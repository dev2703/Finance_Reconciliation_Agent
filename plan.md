# Finance Reconciliation — Architecture Plan

This document describes the **target architecture and requirements**, not completed implementation.
For delivery phases, owners, acceptance criteria, and progress, use [agents.md](agents.md).

> **Numbering:** “Section 5” here means connector architecture. “Phase 5” in
> [agents.md](agents.md#phase-5--tensormux-candidate-ranker) means the TensorMux candidate ranker. Architecture sections
> and delivery phases use separate numbering.

## At a glance

- **Product:** Bank, vendor, customer, and configurable business reconciliation.
- **Pipeline:** Upload → normalize with provenance → deterministic matching → graph matching → TensorMux ranking/investigation → accounting validation → approval → audited action.
- **Stack:** Next.js frontend, FastAPI and a worker, PostgreSQL, and object storage.
- **LLM boundary:** Compact evidence only; accounting arithmetic and final validation remain deterministic.
- **AO boundary:** Development supervision only. FastAPI/PostgreSQL own runtime workflow state.
- **Evaluation:** Ground-truth benchmarks, hard negatives, financial exposure, reliability, latency, and cost.

## Contents

- [Section 0. Core architecture decisions](#section-0-core-architecture-decisions)
- [Section 1. System topology](#section-1-system-topology)
- [Section 2. Repository architecture](#section-2-repository-architecture)
- [Section 3. Canonical financial data model](#section-3-canonical-financial-data-model)
- [Section 4. Ingestion architecture](#section-4-ingestion-architecture)
- [Section 5. Connector architecture](#section-5-connector-architecture)
- [Section 6. Plaid and Stripe sandboxes](#section-6-plaid-and-stripe-sandboxes)
- [Section 7. Reconciliation engine](#section-7-reconciliation-engine)
- [Section 8. Three-stage matching architecture](#section-8-three-stage-matching-architecture)
- [Section 9. How to evaluate the TensorMux ranker](#section-9-how-to-evaluate-the-tensormux-ranker)
- [Section 10. Ground-truth datasets and how each is used](#section-10-ground-truth-datasets-and-how-each-is-used)
- [Section 11. Investigation agent architecture](#section-11-investigation-agent-architecture)
- [Section 12. LLM usage architecture](#section-12-llm-usage-architecture)
- [Section 13. Application-agent design and AO development tooling](#section-13-application-agent-design-and-ao-development-tooling)
- [Section 14. Runtime workflow state machine](#section-14-runtime-workflow-state-machine)
- [Section 15. Accounting validator](#section-15-accounting-validator)
- [Section 16. Approval policy engine](#section-16-approval-policy-engine)
- [Section 17. Database architecture](#section-17-database-architecture)
- [Section 18. API contracts](#section-18-api-contracts)
- [Section 19. TensorMux placement](#section-19-tensormux-placement)
- [Section 20. Neatlogs / observability](#section-20-neatlogs--observability)
- [Section 21. Frontend technical architecture](#section-21-frontend-technical-architecture)
- [Section 22. Reporting architecture](#section-22-reporting-architecture)
- [Section 23. Idempotency and failure recovery](#section-23-idempotency-and-failure-recovery)
- [Section 24. Evaluation architecture](#section-24-evaluation-architecture)
- [Section 25. Financial-risk metrics](#section-25-financial-risk-metrics)
- [Section 26. Accuracy / reliability / cost / speed experiment](#section-26-accuracy--reliability--cost--speed-experiment)
- [Section 27. TensorMux evaluation data flow](#section-27-tensormux-evaluation-data-flow)
- [Section 28. Security boundaries for MVP](#section-28-security-boundaries-for-mvp)
- [Section 29. Deployment architecture](#section-29-deployment-architecture)
- [Section 30. Technical build sequence](#section-30-technical-build-sequence)

## Section 0. Core architecture decisions

### Product boundary

The system reconciles financial records across one or more source systems, constructs transaction lineage, classifies exceptions, gathers evidence, proposes/executes permitted resolutions, and records an auditable workflow state.

**Supported reconciliation families:**

- Bank reconciliation: bank ↔ GL / cash ledger / subledger.
- Vendor reconciliation: PO/invoice ↔ AP ledger ↔ payments ↔ bank/processor.
- Customer reconciliation: AR invoice ↔ receipts ↔ processor/bank ↔ GL.
- Business-specific reconciliation: configurable source pairs/graphs using a common normalized transaction schema and matching configuration.

### Reliability principle

**The LLM is not the reconciliation engine and is not the source of accounting truth. The execution order is:**

parse/validate → deterministic matching → graph/path matching → TensorMux ranking and bounded investigation only when needed → accounting validation → approval policy → action

### Agent principle

AO (Agent Orchestrator at aoagents.dev) is a coding-agent supervisor/IDE used to parallelize development, not the runtime workflow engine of the product. Runtime workflow state belongs to FastAPI + PostgreSQL; application agents are invoked from that workflow. AO provides isolated coding-agent workspaces, branches, PR/CI/review coordination, etc. [^sources]

### Model principle

Use GLM-4.7-Flash MoE 30B access through TensorMux for LLM tasks. Do not send the full ledger to the model. The LLM receives compact, relevant evidence bundles and structured cases only.

### Integration principle

MVP uses uploads. Integration adapters are implemented behind the same normalized data contracts so the source can later be Stripe, Plaid, ERP/accounting software, credit-card feeds, or a customer-specific API without changing reconciliation logic.

## Section 1. System topology

```text
                              Next.js / TypeScript
                         Vercel + GitHub CI/CD
                                  │
                                  ▼
                           FastAPI API layer
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
        Upload Service       Recon Workflow      Review API
              │                   │                   │
              ▼                   ▼                   ▼
       Ingestion Pipeline   Runtime Workflow     Approval Queue
              │                   │                   │
              └──────────────┬────┴────┬──────────────┘
                             ▼         ▼
                     PostgreSQL     Object Storage
                             │
                             ▼
                  Canonical Financial Model
                             │
                             ▼
                  Reconciliation Engine
                             │
             ┌───────────────┼────────────────┐
             ▼               ▼                ▼
       Deterministic      Graph/Path    Evidence Builder
          Rules             Engine              │
             │               │                  │
             └───────────────┼──────────────────┘
                             ▼
                      Exception Router
                             │
                             ▼
                    Application Agents
                             │
                             ├── Investigator
                             ├── Evidence/Document
                             ├── Summary
                             └── Extraction fallback
                             │
                             ▼
                         TensorMux
                             │
                             ▼
                    GLM-4.7-Flash MoE 30B
                             │
                             ▼
                     Structured Agent Output
                             │
                             ▼
                    Accounting Validator
                             │
                             ▼
                       Policy Engine
                         /        \
                        /          \
                  AUTO ACTION     HUMAN REVIEW
                        \          /
                         \        /
                          ▼      ▼
                       Journal / Reconcile / Audit
```

## Section 2. Repository architecture

**Recommended monorepo:**

```text
cfo-autopilot/
├── apps/
│   ├── web/                         # Next.js frontend
│   └── api/                         # FastAPI application
├── packages/
│   ├── contracts/                   # shared schemas / OpenAPI generated TS
│   ├── ui/                          # reusable frontend components
│   └── config/                      # shared configuration
├── services/
│   ├── ingestion/
│   ├── reconciliation/
│   ├── matching/
│   │   └── tensormux/               # ranking/evidence orchestration
│   ├── graph/
│   ├── agents/
│   ├── policy/
│   ├── audit/
│   └── reporting/
├── connectors/
│   ├── csv/
│   ├── xlsx/
│   ├── pdf/
│   ├── plaid/
│   ├── stripe/
│   └── accounting/
├── evaluation/
│   ├── datasets/
│   ├── runners/
│   ├── metrics/
│   └── reports/
├── infra/
│   ├── docker/
│   └── migrations/
└── docs/
```

Keep services as Python modules/packages first. Do not split them into network microservices unless scaling requires it.

## Section 3. Canonical financial data model

Every source adapter converts raw records into a common schema.

### 3.1 Core entities

- Organization
- FinancialAccount
- SourceSystem
- Document
- Party
- Invoice
- PurchaseOrder
- Payment
- Settlement
- BankTransaction
- LedgerEntry
- ReconciliationRun
- ReconciliationItem
- ExceptionCase
- EvidenceItem
- Investigation
- ProposedAction
- Approval
- AuditEvent

### 3.2 Canonical transaction envelope

```text
FinancialRecord(
    id: str,
    organization_id: str,
    source_system: str,
    source_record_id: str,
    record_type: str,
    account_id: str | None,
    party_id: str | None,
    invoice_id: str | None,
    amount: Decimal | None,
    currency: str | None,
    transaction_date: date | None,
    posting_date: date | None,
    description: str | None,
    reference: str | None,
    status: str | None,
    metadata: dict,
    provenance: Provenance
)
```

Decimal must be used for money; never binary floating point for accounting arithmetic.

### 3.3 Provenance

**Every canonical field should retain:**

- source file/API
- page/sheet/row where applicable
- original field name
- extraction method
- parser confidence
- transformation history.

This provenance is later surfaced as evidence and makes corrections auditable.

## Section 4. Ingestion architecture

### 4.1 Upload-first MVP

**Frontend:**

- drag/drop → upload → progress → classify → parse → preview → confirm → import

**Backend:**

```text
POST /documents/upload
       ↓
Object storage
       ↓
Document record
       ↓
Ingestion job
       ↓
Document classifier
       ↓
Parser selection
       ↓
Schema extraction
       ↓
Normalization
       ↓
Validation
       ↓
Import preview
```

The user should be able to inspect extracted tables before they enter reconciliation.

### 4.2 File types

**MVP:**

- CSV
- XLSX
- PDF

**Later:**

- OFX/QFX
- JSON exports
- accounting-system exports
- direct APIs

### 4.3 PDF/table ingestion

Financial PDFs must be treated as layout documents, not plain text.

**Pipeline:**

```text
PDF
 │
 ├── text-native? ── yes ──► extract text + word coordinates
 │
 └── scanned? ───── no ───► render page + OCR
                              │
                              ▼
                       table detection
                              │
                              ▼
                    table structure recognition
                              │
                              ▼
                   cell/row/column reconstruction
                              │
                              ▼
                    header / data-role detection
                              │
                              ▼
                         normalization
```

For tables without visible margins/grid lines, do not rely on line-based extraction alone. Use page/image coordinates, text bounding boxes, and table-structure recognition. Microsoft’s Table Transformer (TATR) is specifically designed for table detection and structure recognition from PDFs/images and returns cell-level structure; its inference pipeline can consume OCR/PDF word tokens plus their bounding boxes. [^sources]

**Recommended parser stack:**

- native PDF text + coordinates via a PDF parser
- TATR for table detection/structure when table geometry is complex
- OCR only for scanned pages
- deterministic cell reconstruction
- LLM fallback only for unresolved schema/semantic interpretation.

Do not send a whole annual report to GLM. Crop/select only the relevant page/table regions and provide structured extracted cells plus nearby headings.

### 4.4 Financial table normalization

**A table may arrive as:**

```text
Account       FY2025       FY2024
Revenue       1,234,000    1,104,000
COGS            500,000      450,000
```

or without headers/margins, with repeated headers across pages, merged cells, negative values in parentheses, footnotes, or units such as in thousands.

**Normalization must handle:**

- repeated headers
- merged/spanning cells
- page breaks
- parenthetical negatives
- currency symbols
- 000s/millions scaling
- dates and fiscal periods
- subtotal/total rows
- footnotes
- columns with blank spacing rather than borders.

A post-parser schema validator should detect impossible outcomes such as a balance sheet that no longer balances after extraction.

## Section 5. Connector architecture

**Use an adapter interface:**

```python
class SourceConnector(Protocol):
    def discover(self) -> SourceMetadata: ...
    def fetch(self, cursor: str | None = None) -> list[RawRecord]: ...
    def normalize(self, raw: RawRecord) -> FinancialRecord: ...
```

**Adapters:**

- CSV/XLSX/PDF adapters       ← MVP
- Plaid connector             ← bank/account feeds
- Stripe connector            ← payments/settlements
- Accounting connector        ← ERP/accounting software
- Credit account connector    ← card/credit feeds
- Custom connector            ← business-specific source

All adapters terminate in the canonical data model.

## Section 6. Plaid and Stripe sandboxes

Sandboxes should be used as integration-test environments, not as the only demo data source.

Plaid Sandbox supports API and Link testing, test Items, configurable/custom test data, transaction simulation, and Sandbox-only webhook triggers. Plaid also exposes /sandbox/transactions/create for adding custom transactions to a Sandbox Item. [^sources]

Stripe Sandboxes are isolated environments for testing payment behavior without real money movement and can be used to create/test payments and simulated events. [^sources]

**Recommended architecture:**

```text
                 Connector contract
                       │
            ┌──────────┴──────────┐
            ▼                     ▼
       CSV/PDF/XLSX         Plaid/Stripe
         adapters             sandbox
            │                     │
            └──────────┬──────────┘
                       ▼
               Canonical records
```

The deterministic benchmark remains the authoritative evaluation source because it has exact ground truth.

## Section 7. Reconciliation engine

The engine should support multiple reconciliation templates.

### 7.1 Bank reconciliation

- Bank transactions ↔ GL / cash ledger

**Rules include:**

- exact reference match
- exact amount/date match
- tolerance windows
- known outstanding items
- fee relationships
- timing/clearing windows
- one-to-many and many-to-one settlements.

### 7.2 Vendor reconciliation

- PO ↔ Invoice ↔ AP ledger ↔ Payment ↔ Bank

**Supports:**

- 2-way/3-way matching
- partial invoices
- partial payments
- duplicate invoices
- overpayment/underpayment
- invoice/payment allocation.

### 7.3 Customer reconciliation

- Invoice ↔ Receipt ↔ Processor ↔ Bank ↔ AR ledger

**Supports:**

- partial payment
- split payment
- remittance references
- refunds/chargebacks
- unapplied cash.

### 7.4 Business-specific reconciliation

**Define a source graph:**

```yaml
reconciliation_type: custom
nodes:
  - orders
  - processor_events
  - settlements
  - bank_transactions
  - ledger
edges:
  - orders -> processor_events
  - processor_events -> settlements
  - settlements -> bank_transactions
  - bank_transactions -> ledger
```

Each edge can specify matching fields, date windows, amount tolerances, and cardinality.

## Section 8. Three-stage matching architecture

### Stage A — deterministic matching

Fast, explainable, no LLM.

**Examples:**

- exact invoice ID
- exact payment ID
- exact settlement ID
- exact reference
- exact amount + currency
- known processor fee formula
- allowed timing window

**Every rule should emit a reason code:**

- MATCH_EXACT_REFERENCE
- MATCH_EXACT_AMOUNT_DATE
- MATCH_KNOWN_SETTLEMENT_PATTERN
- MATCH_FEE_VARIANCE
- MATCH_TIMING_WINDOW

### Stage B — graph/path matching

This is not necessarily “trained”. It is an algorithmic search/optimization layer.

**Represent records as a graph:**

```text
Invoice ──paid_by──► Payment
Payment ──processed_by──► ProcessorEvent
ProcessorEvent ──included_in──► SettlementBatch
SettlementBatch ──deposited_as──► BankTxn
BankTxn ──posted_as──► GLEntry
```

Support many-to-one and one-to-many paths.

### Candidate graph construction

- create entities/nodes
- create deterministic candidate edges using blocking keys
- score edge compatibility using amount/date/reference/party constraints
- enumerate small candidate paths

solve for a consistent subgraph subject to conservation and cardinality constraints.

**Possible algorithms:**

- bipartite matching for pairwise reconciliation
- min-cost flow for one-to-many/many-to-one allocation
- beam search over candidate paths for multi-hop lineage
- connected-component analysis for duplicate/split groups
- constraint solving for amount conservation.

**For a payment-to-bank example:**

```text
Payment = 1000
Fee = 30
FX = 5
Expected settlement = 965
Bank deposit = 965
```

The path is valid even though no single row equals the original payment amount.

### Stage C — TensorMux candidate ranking

Use TensorMux for ambiguous candidate ranking, not basic accounting arithmetic. Send one complete
competing candidate group so the model cannot score hand-picked pairs without their rivals.

**Evidence groups:**

```text
amount:
  abs_delta
  relative_delta
  fee-adjusted delta

date:
  days_between
  business_days_between

text:
  merchant similarity
  reference similarity
  deterministic description similarity

entity:
  vendor/customer match
  account match
  historical relationship frequency

graph:
  path length
  path reliability
  number of supporting records
```

The evidence builder computes these facts deterministically. TensorMux receives only bounded,
relevant records and may not recompute money, invent candidates, or access the database directly.

One competing group is the complete connected component of blocked candidate edges sharing any
source or target record. Before calling TensorMux, assert every edge in that component is present.
Allow at most 100 candidates, 30 evidence items, and 24,000 input tokens. Do not truncate an
oversized group; return `UNRESOLVED/GROUP_TOO_LARGE`.

**Canonical group output:**

```text
{
  "group_id": "group_123",
  "ranked_candidates": [{
    "candidate_id": "cand_123",
    "classification": "HUMAN_REVIEW",
    "confidence": 0.982,
    "reason_codes": [...],
    "supporting_evidence_ids": [...],
    "contradicting_evidence_ids": [...],
    "unresolved_questions": []
  }],
  "no_match": false,
  "decision_manifest_hash": "...",
  "prompt_hash": "...",
  "schema_hash": "...",
  "tensormux_route": "reconciliation-ranker",
  "backend_model_version": "..."
}
```

## Section 9. How to evaluate the TensorMux ranker

Use the ground-truth datasets for prompt development, calibration, and sealed evaluation. There is
no local model training or executable model artifact.

### 9.1 Evaluation examples

Construct positive and negative pairs/groups from known ground truth.

**Positive:**

- payment P ↔ settlement S

**Negative:**

- P ↔ unrelated settlement

**Hard negatives:**

- same amount, wrong date
- same vendor, wrong invoice
- correct invoice but wrong settlement
- legitimate timing difference
- valid split payment
- fee-related amount difference.

### 9.2 Sealed split strategy

Never randomly split individual rows from the same generated world into train and test if this leaks templates.

**Prefer:**

- generator seeds
- scenario IDs
- failure categories
- entities
- months
- held out by group.

**Example:**

- Development: seeds 1–30
- Validation: seeds 31–35
- Test: seeds 36–40

Then create a second, unpublished custom hard set with unseen combinations of failure types. Public
ReconRiver and FinRCA results must be reported separately because a hosted model may have encountered
public benchmark material during pretraining. The authoritative production gate is the unpublished
set with at least 500 complete candidate groups and 100 hard-negative groups.

### 9.3 Evaluation pipeline

```text
ReconRiver / FinRCA / custom generated cases
             ↓
       candidate generator
             ↓
        evidence builder
             ↓
      development / calibration / sealed test split
             ↓
   TensorMux prompt + schema + pinned route
             ↓
     empirical threshold evaluation
             ↓
       held-out evaluation
             ↓
       decision manifest + version
```

Log TensorMux route, pinned backend model version, prompt/schema/evidence-builder hashes, dataset-generation seed,
dataset hashes, thresholds, inference parameters (`temperature`, `top_p`, `max_tokens`, response
format), and metrics. Read the observed backend version from a configured TensorMux response
field/header; missing or mismatched versions fail closed. Any bundle change requires reevaluation,
and CI must assert the runtime manifest hash equals the last evaluated manifest hash.

The manifest also fixes the ranking budgets. Initial maximums are one logical model call and three
transport attempts per group, 24,000 input tokens, 2,000 output tokens, 90 seconds, and USD 0.10
estimated cost per group; and 1,000 groups, 26,000,000 total tokens, 30 minutes, and USD 50 per run.
Deployments may lower these values. Raising one changes the manifest hash and requires reevaluation.

Cache validated outputs by `(decision_manifest_hash, evidence_bundle_hash)`. For nondeterminism
measurement, bypass the cache and run every unpublished sealed group three times. Classification
disagreement must be <= 1%; any candidate that disagrees remains unresolved.

### 9.4 Thresholding

Do not select the threshold solely for F1. Select only a human-review threshold and unresolved
boundary. TensorMux never makes an automatic accounting decision.

The authoritative unpublished sealed set must meet all of these frozen gates:

- `HUMAN_REVIEW` precision >= 98%; a selected candidate is correct only if it is a ground-truth
  link, so the denominator is every candidate classified `HUMAN_REVIEW`
- hard-negative review false-positive rate <= 1%
- unresolved-group count at least 10% lower than deterministic+graph on the identical set
- no threshold changes after examining sealed results.

Exact deterministic rules may remain eligible for automatic action only after accounting validation
and policy approval; policy must never use TensorMux ranker confidence as an `AUTO_APPROVE` input.

### 9.5 Local-model migration and removal

The merged local-model implementation is superseded; it is not a second production ranking path.
The first migration PR deletes the local `/demo/ml-review` behavior and any alias,
`ML_MODEL_DIRECTORY`, and the two local Phase 5 runtime/demo documents. It also removes the optional
synthetic-artifact statement from `docs/deployment.md`. API tests must prove no local-artifact route
remains. The PR moves provider-neutral dataset contracts/adapters into `evaluation/datasets/`
without importing training code. Historical `services/ml/` training, calibration, artifact, model,
workflow, selection, feature, and contract modules plus `evaluation/train_ml/` are deleted or moved
under `evaluation/legacy_ml/`; no API or worker may import them.

Once TensorMux ranking passes its sealed acceptance gate, remove any remaining
`evaluation/legacy_ml/` experiments. Retain only provider-neutral dataset adapters and evaluation
metrics under `evaluation/`. There must be one production inference boundary: the versioned
TensorMux decision manifest and shared gateway.

Remove `scikit-learn`, `xgboost`, `joblib`, and `sentence-transformers` from
`requirements-runtime.txt` and `pyproject.toml` `[project].dependencies`. `torch` and `transformers`
remain only in the PDF/TATR worker dependency set, not because of ranking. Extend
`tests/test_runtime_dependencies.py` with the prohibited-package assertion. Architecture tests must
also verify that production starts without model files, the runtime import graph contains no
`joblib.load`/`model.joblib` path, TensorMux manifest versions are recorded on outputs, and gateway
failure yields `UNRESOLVED` without accounting mutation.

## Section 10. Ground-truth datasets and how each is used

### 10.1 ReconRiver

ReconRiver is the primary operational reconciliation benchmark. It is deterministic and synthetic, with canonical payments leading into an internal ledger, processor events, bank settlements, and expected reconciliation ground truth. It provides clean-settlement, mixed-exceptions, month-end-close, and failure-recovery scenario packs, including 1K and 10K-scale cases. [^sources]

**Use it for:**

- deterministic matcher validation
- graph/path reconciliation
- exception taxonomy
- end-to-end reconciliation accuracy
- scale/performance tests
- failure recovery/idempotency tests.

### 10.2 FinRCA-AI-Bench

FinRCA is a deterministic synthetic benchmark focused on financial reconciliation and root-cause analysis. It includes tables such as vendors, POs, invoices, payments, allocations, GL entries, bank transactions/statements, approvals and audit logs; its generated benchmark covers multiple failure categories and legitimate/no-failure cases. [^sources]

**Use it for:**

- exception detection
- root-cause classification
- evidence retrieval
- proposed resolution correctness
- hard-negative evaluation.

### 10.3 FinBalance

FinBalance contains document/OCR text, rendered PDF-style assets, trial balances, account taxonomies, expected journal entries, final balance sheets, contradiction labels, and multi-document accounting scenarios across several industries and complexity levels. It can also generate fresh datasets. [^sources]

**Use it for:**

- PDF/document ingestion
- accounting-document understanding
- multi-document evidence grounding
- journal-entry validation
- contradiction detection
- document parser evaluation.

### 10.4 Custom benchmark

**Build a small project-specific suite combining:**

- clean matches
- fee variance
- timing difference
- duplicate
- partial payment
- split settlement
- missing bank item
- missing ERP item
- wrong allocation
- wrong period
- ambiguous remittance
- messy PDF table
- scanned PDF
- hard negative

Every custom case must have exact ground truth.

## Section 11. Investigation agent architecture

The investigation agent is bounded and evidence-driven.

It is not called for every transaction.

**Trigger condition:**

```text
unresolved after deterministic
AND
unresolved/low-confidence after graph + TensorMux ranking
```

### Input case

```text
{
  "case_id": "EX-8291",
  "exception_type": "AMOUNT_MISMATCH",
  "candidate_records": [...],
  "computed_variance": 260.00,
  "currency": "USD",
  "reconciliation_policy": {...}
}
```

### Agent tool set

```text
search_records()
get_related_records()
search_documents()
get_document_page()
get_invoice()
get_payment()
get_settlement()
get_bank_transaction()
get_ledger_entry()
get_accounting_policy()
get_historical_matches()
calculate_variance()       # deterministic tool
validate_conservation()    # deterministic tool
propose_resolution()      # schema-only proposal
```

### Investigation loop

```text
Case
 ↓
Hypothesis generation
 ↓
Choose one tool
 ↓
Retrieve evidence
 ↓
Update evidence set
 ↓
Check stopping criteria
 ├── sufficient evidence → resolution
 └── insufficient → next tool
```

### Token-control design

**Enforce:**

- max tool calls per case
- maximum evidence rows per call
- maximum context bytes/tokens
- no repeated identical searches
- structured tool results rather than raw database dumps
- early stop once sufficient evidence is found
- deterministic calculations outside the LLM
- evidence bundle deduplication.

**Example policy:**

```text
max_llm_turns = 4
max_tool_calls = 8
max_evidence_records = 30
```

Adjust from evaluation rather than hard-code blindly.

The goal is not “let the agent reason until it is happy”; it is “retrieve the minimum evidence needed to close the case.”

## Section 12. LLM usage architecture

GLM-4.7-Flash MoE 30B should be the single available reasoning model behind TensorMux.

**Use cases:**

### A. Extraction fallback

Only when deterministic/OCR/table parsing confidence is insufficient.

**Input:**

- cropped table/page
- extracted tokens/cells
- schema target
- nearby headings/footnotes.

Output strict JSON.

### B. Exception investigation

Only unresolved cases.

Input = compact evidence bundle, not source database.

### C. Summary generation

Use already-computed structured metrics.

The LLM should not calculate KPI values; it verbalizes known values.

### D. Review explanation

Convert evidence + validated decision into clear reviewer language.

### E. Candidate ranking

Rank one complete graph-blocked competing group against the canonical Phase 5 schema. Apply the
ranking-specific group, token, time, call-count, and cost budgets. Never truncate a group and never
return an automatic accounting action.

## Section 13. Application-agent design and AO development tooling

**Runtime application agents:**

```text
Recon Controller
 ├── Investigation Agent
 ├── Document Extraction Agent
 ├── Summary Agent
 └── Review Explanation Agent
```

Use a single controller workflow where possible. Specialist agents should be invoked as bounded capabilities, not as free-form autonomous agents.

AO at aoagents.dev is used separately by the development team to supervise multiple coding agents working in isolated workspaces/branches and connecting them to GitHub, CI, PRs and reviews. [^sources]

## Section 14. Runtime workflow state machine

```text
UPLOADED
  ↓
INGESTING
  ↓
PARSED
  ↓
VALIDATED
  ↓
READY
  ↓
MATCHING
  ├── RECONCILED
  └── EXCEPTION_DETECTED
          ↓
      INVESTIGATING
          ↓
       EVIDENCE_READY
          ↓
     ROOT_CAUSE_FOUND
          ↓
   RESOLUTION_PROPOSED
          ↓
     POLICY_EVALUATION
       /          \
 AUTO_APPROVE    HUMAN_REVIEW
      |               |
      └──────┬────────┘
             ↓
         VALIDATING
             ↓
          POSTING
             ↓
         COMPLETED
```

Every transition is persisted and idempotent.

## Section 15. Accounting validator

**Before any write/action:**

- amount arithmetic correct?
- Debit = credit?
- currency valid?
- period valid?
- duplicate action?
- existing reconciliation?
- source records still valid?
- policy allows action?
- LLM-generated journal entries are proposals only.

All final journal entries are generated/validated by deterministic code.

## Section 16. Approval policy engine

Policy is code/configuration, not a prompt.

```yaml
rules:
  - condition:
      exact_match: true
      evidence_complete: true
      amount_below: 5000
    action: AUTO_APPROVE

  - condition:
      known_variance: true
      evidence_complete: true
      amount_below: 5000
    action: AUTO_APPROVE

  - condition:
      amount_above: 5000
    action: HUMAN_REVIEW

  - condition:
      root_cause_confidence_below: 0.95
    action: HUMAN_REVIEW

  - condition:
      unresolved: true
    action: ESCALATE
```

**Policy output:**

```json
{
  "decision": "HUMAN_REVIEW",
  "reason_codes": ["HIGH_VALUE", "NON_STANDARD_VARIANCE"],
  "required_evidence": ["bank_txn", "settlement", "invoice"]
}
```

## Section 17. Database architecture

Use PostgreSQL as the primary system of record.

**Recommended tables:**

- organizations
- source_systems
- financial_accounts
- parties
- raw_documents
- document_pages
- document_regions
- extracted_tables
- extracted_cells
- invoices
- purchase_orders
- payments
- settlements
- bank_transactions
- ledger_entries
- processor_events
- reconciliation_runs
- reconciliation_items
- match_candidates
- match_decisions
- exception_cases
- investigations
- evidence_items
- proposed_actions
- approvals
- journal_entries
- audit_events
- agent_runs
- model_calls
- tensor_mux_ranking_decisions
- tensor_mux_decision_manifests

`tensor_mux_ranking_decisions` stores the group and evidence hashes, validated response, distinct
terminal reason, manifest hash/version, observed backend version, model-call IDs, and timestamps.
The manifest table stores immutable prompt/schema/evidence-builder hashes, route/backend pins,
inference parameters, evaluated dataset hashes, thresholds, metrics, and approval state.

Object storage holds source PDFs/XLSX/CSV and page/table images. PostgreSQL stores metadata, normalized records, provenance and workflow state.

**For the graph, start with relational adjacency tables:**

- entity_nodes
- entity_edges
- candidate_edges

Do not introduce a graph database in the MVP.

Redis/background queue is optional. For the MVP, FastAPI background jobs or a simple worker queue can run ingestion/reconciliation. Introduce Redis/Celery/RQ only when concurrency requires it.

## Section 18. API contracts

### Upload

```text
POST /api/documents/upload
```

### Ingestion status

```text
GET /api/documents/{document_id}
GET /api/documents/{document_id}/preview
```

### Start reconciliation

```text
POST /api/reconciliation/runs
```

**Body:**

```json
{
  "type": "bank",
  "source_ids": ["bank_1", "ledger_1"],
  "period": {"start": "2026-01-01", "end": "2026-01-31"}
}
```

### Results

```text
GET /api/reconciliation/runs/{run_id}
GET /api/reconciliation/runs/{run_id}/items
GET /api/reconciliation/runs/{run_id}/exceptions
```

### Investigation

```text
POST /api/exceptions/{exception_id}/investigate
GET  /api/exceptions/{exception_id}/investigation
```

### Review

```text
POST /api/exceptions/{exception_id}/approve
POST /api/exceptions/{exception_id}/reject
POST /api/exceptions/{exception_id}/escalate
```

### Reports

```text
GET /api/reports/reconciliation/{run_id}
GET /api/reports/exceptions/{run_id}
GET /api/reports/audit/{run_id}
```

All APIs return machine-readable IDs/statuses; frontend rendering is separate.

## Section 19. TensorMux placement

TensorMux is the system's only model inference gateway and the center of candidate ranking,
extraction fallback, investigation, summary, and review explanation. FastAPI/PostgreSQL still own
workflow state, and deterministic code still owns accounting facts, validation, and mutation.

**Architecture:**

```text
Application agent
        ↓
OpenAI-compatible client
        ↓
TensorMux
        ↓
GLM-4.7-Flash MoE 30B
```

Keep provider/model selection behind configuration.

**Expose model-call telemetry:**

- model
- prompt_tokens
- completion_tokens
- latency_ms
- retry_count
- status
- estimated_cost
- case_id
- agent_run_id

Even with one available model, the gateway gives us one stable inference boundary and makes later model routing possible without changing application agent code.

## Section 20. Neatlogs / observability

**Trace:**

```text
reconciliation run
  ↓
exception case
  ↓
agent run
  ├── model call
  ├── tool call
  ├── tool call
  ├── model call
  └── policy decision
```

Store a local minimal agent_runs record regardless of external observability availability.

**Track:**

- total run time
- deterministic matching time
- graph matching time
- TensorMux ranking time
- agent time
- tool-call count
- model tokens
- model latency
- failure/retry counts
- final decision.

## Section 21. Frontend technical architecture

Next.js App Router + TypeScript.

**Core routes:**

- /dashboard
- /reconciliation
- /reconciliation/[id]
- /exceptions
- /exceptions/[id]
- /documents
- /documents/[id]
- /reports
- /settings/integrations

**Components:**

- UploadDropzone
- DocumentProcessingStatus
- ReconciliationTable
- MatchBadge
- ExceptionQueue
- EvidencePanel
- TransactionGraph
- InvestigationTimeline
- ApprovalPanel
- ReportCharts
- AgentTracePanel

Use a professional finance visual system inspired by Maximor’s restrained enterprise-finance feel: neutral surfaces, compact data-dense tables, deliberate accent color, strong hierarchy, and clear states. UFO-style/graph visualization is used selectively for lineage and agent execution rather than as the entire visual language.

**Frontend state:**

- TanStack Query for server state
- local component state for transient UI
- typed API client generated from OpenAPI.

**Charts:**

- reconciliation progress
- exception composition
- amount-at-risk
- automation rate
- aging of unresolved items
- performance/evaluation metrics.

## Section 22. Reporting architecture

Reports should be generated primarily from SQL/structured state, not by LLM.

**Report pipeline:**

```text
Postgres metrics
   ↓
metric computation
   ↓
report JSON
   ↓
Next.js charts/tables
   ↓
optional LLM narrative summary
```

**Report types:**

- reconciliation summary
- exceptions by root cause
- unresolved/approval queue
- amount at risk
- evidence coverage
- audit history
- agent performance.

## Section 23. Idempotency and failure recovery

**Every external/import operation gets an idempotency key:**

- source_system + source_record_id + source_version

Do not duplicate records when a job restarts.

**Reconciliation run state must support restart:**

- checkpoint → resume → preserve completed matches → continue unresolved work

ReconRiver’s failure-recovery scenarios should be used to validate this behavior. [^sources]

## Section 24. Evaluation architecture

**Three primary benchmark loops:**

### Matching benchmark

**Measures:**

- pairwise match precision/recall
- one-to-many allocation accuracy
- false match rate
- unmatched recall.

### Exception/RCA benchmark

**Measures:**

- exception detection precision/recall
- root cause accuracy
- evidence precision/recall
- resolution accuracy
- hard-negative false-positive rate.

### End-to-end benchmark

**Measures:**

- complete reconciliation accuracy
- auto-resolution precision
- human-review routing accuracy
- financial exposure of incorrect autonomous actions
- workflow completion rate.

FinRCA’s explicit root-cause/evidence/resolution structure and legitimate/no-failure cases should be used to make these metrics meaningful. [^sources]

## Section 25. Financial-risk metrics

Do not report only classification accuracy.

**Compute:**

- Auto-approval precision
- Auto-approval recall
- Human-routing precision
- False-positive financial exposure
- False-negative financial exposure
- Amount correctly reconciled
- Automation rate

**Example:**

```text
financial_false_positive_exposure
= sum(amount of incorrectly auto-resolved cases)
```

This should be one of the headline metrics.

## Section 26. Accuracy / reliability / cost / speed experiment

**Compare at minimum:**

### Baseline A

Deterministic-only matcher.

### Baseline B

Deterministic + graph + TensorMux ranking.

### System C

Deterministic + graph + TensorMux ranking + bounded GLM investigation.

**Optionally:**

### System D

Same as C with tighter evidence selection/tool-call limits.

**Record:**

- accuracy
- RCA accuracy
- hard-negative FP rate
- financial exposure
- latency
- LLM calls/case
- tokens/case
- cost/case
- failure rate

This demonstrates whether the agentic layer creates measurable value rather than merely increasing complexity.

## Section 27. TensorMux evaluation data flow

```text
                 DATA SOURCES
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
    ReconRiver      FinRCA       FinBalance
        │             │              │
        ▼             ▼              ▼
    Matching      RCA/Evidence   Documents/JE
        │             │              │
        └─────────────┼──────────────┘
                      ▼
                Custom benchmark
                      │
          ┌───────────┴────────────┐
          ▼                        ▼
   DEVELOPMENT/CALIBRATION     SEALED TESTING
          │                        │
 TensorMux decision bundle  End-to-end workflow
          │                        │
          ▼                        ▼
 versioned manifest            metrics
```

Do not use test-set labels as prompts or retrieval documents.

## Section 28. Security boundaries for MVP

No production authentication stack is required for the hackathon.

**Still enforce:**

- secrets only in environment variables
- uploaded files stored outside source control
- sandbox credentials isolated
- source provenance on every imported record
- no raw credentials in agent context
- no unrestricted SQL tool for agents
- tool allowlists
- structured write endpoints
- audit log for every mutation.

## Section 29. Deployment architecture

Modal is not required by this architecture. The initial deployment may use Vercel for Next.js and
short control-plane requests, with a separately selected durable worker runtime for ingestion,
PDF/OCR, reconciliation, and TensorMux jobs. TensorMux contracts, manifests, idempotency, and
fail-closed behavior must remain portable across worker platforms.

```text
GitHub
  │
  ├── frontend build → Vercel
  │
  └── backend/container → selected runtime
                         │
                         ├── FastAPI
                         ├── Worker
                         ├── PostgreSQL
                         └── Object storage
```

- TensorMux → model inference endpoint
- Neatlogs  → observability

**Use GitHub CI for:**

- type checks
- Python tests
- frontend tests
- linting
- API schema validation
- evaluation smoke tests.

## Section 30. Technical build sequence

**The implementation order should be:**

- canonical schemas
- database/migrations
- upload/object storage
- CSV/XLSX ingestion
- PDF/table extraction
- deterministic reconciliation
- graph/path matcher
- TensorMux candidate ranker
- evaluation harness
- Runtime application-agent integration
- TensorMux/GLM integration
- evidence/reasoning tools
- policy/approval engine
- reports/audit
- frontend integration
- Plaid/Stripe adapters
- performance/reliability benchmark
- final demo instrumentation.

The detailed phase breakdown and delivery tracking are in [agents.md](agents.md).

## Source notes

[^sources]: The supplied document contained internal chat citation IDs without source URLs. The associated claims are retained, but those references need verification and replacement with usable links. No external-source verification was performed in this formatting pass.
