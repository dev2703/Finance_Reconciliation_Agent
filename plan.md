0. Core architecture decisions

Product boundary

The system reconciles financial records across one or more source systems, constructs transaction lineage, classifies exceptions, gathers evidence, proposes/executes permitted resolutions, and records an auditable workflow state.

Supported reconciliation families:

Bank reconciliation: bank ↔ GL / cash ledger / subledger.

Vendor reconciliation: PO/invoice ↔ AP ledger ↔ payments ↔ bank/processor.

Customer reconciliation: AR invoice ↔ receipts ↔ processor/bank ↔ GL.

Business-specific reconciliation: configurable source pairs/graphs using a common normalized transaction schema and matching configuration.

Reliability principle

The LLM is not the reconciliation engine and is not the source of accounting truth. The execution order is:

parse/validate → deterministic matching → graph/path matching → ML scoring → bounded LLM investigation only when needed → accounting validation → approval policy → action

Agent principle

AO (Agent Orchestrator at aoagents.dev) is a coding-agent supervisor/IDE used to parallelize development, not the runtime workflow engine of the product. Runtime workflow state belongs to FastAPI + PostgreSQL; application agents are invoked from that workflow. AO provides isolated coding-agent workspaces, branches, PR/CI/review coordination, etc. citeturn136401search1turn136401search9

Model principle

Use GLM-4-7B-Flash MoE 30B access through TensorMux for LLM tasks. Do not send the full ledger to the model. The LLM receives compact, relevant evidence bundles and structured cases only.

Integration principle

MVP uses uploads. Integration adapters are implemented behind the same normalized data contracts so the source can later be Stripe, Plaid, ERP/accounting software, credit-card feeds, or a customer-specific API without changing reconciliation logic.

1. System topology

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
       Deterministic      Graph/Path        ML Matcher
          Rules             Engine              │
             │               │                  │
             └───────────────┼──────────────────┘
                             ▼
                      Exception Router
                             │
                             ▼
                    AO Application Agents
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
                    GLM-4-7B-Flash MoE 30B
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

2. Repository architecture

Recommended monorepo:

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
│   ├── graph/
│   ├── ml/
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

Keep services as Python modules/packages first. Do not split them into network microservices unless scaling requires it.

3. Canonical financial data model

Every source adapter converts raw records into a common schema.

3.1 Core entities

Organization
FinancialAccount
SourceSystem
Document
Party
Invoice
PurchaseOrder
Payment
Settlement
BankTransaction
LedgerEntry
ReconciliationRun
ReconciliationItem
ExceptionCase
EvidenceItem
Investigation
ProposedAction
Approval
AuditEvent

3.2 Canonical transaction envelope

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

Decimal must be used for money; never binary floating point for accounting arithmetic.

3.3 Provenance

Every canonical field should retain:

source file/API;

page/sheet/row where applicable;

original field name;

extraction method;

parser confidence;

transformation history.

This provenance is later surfaced as evidence and makes corrections auditable.

4. Ingestion architecture

4.1 Upload-first MVP

Frontend:

drag/drop → upload → progress → classify → parse → preview → confirm → import

Backend:

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

The user should be able to inspect extracted tables before they enter reconciliation.

4.2 File types

MVP:

CSV

XLSX

PDF

Later:

OFX/QFX

JSON exports

accounting-system exports

direct APIs

4.3 PDF/table ingestion

Financial PDFs must be treated as layout documents, not plain text.

Pipeline:

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

For tables without visible margins/grid lines, do not rely on line-based extraction alone. Use page/image coordinates, text bounding boxes, and table-structure recognition. Microsoft’s Table Transformer (TATR) is specifically designed for table detection and structure recognition from PDFs/images and returns cell-level structure; its inference pipeline can consume OCR/PDF word tokens plus their bounding boxes. citeturn595120search0turn595120search2

Recommended parser stack:

native PDF text + coordinates via a PDF parser;

TATR for table detection/structure when table geometry is complex;

OCR only for scanned pages;

deterministic cell reconstruction;

LLM fallback only for unresolved schema/semantic interpretation.

Do not send a whole annual report to GLM. Crop/select only the relevant page/table regions and provide structured extracted cells plus nearby headings.

4.4 Financial table normalization

A table may arrive as:

Account       FY2025       FY2024
Revenue       1,234,000    1,104,000
COGS            500,000      450,000

or without headers/margins, with repeated headers across pages, merged cells, negative values in parentheses, footnotes, or units such as in thousands.

Normalization must handle:

repeated headers;

merged/spanning cells;

page breaks;

parenthetical negatives;

currency symbols;

000s/millions scaling;

dates and fiscal periods;

subtotal/total rows;

footnotes;

columns with blank spacing rather than borders.

A post-parser schema validator should detect impossible outcomes such as a balance sheet that no longer balances after extraction.

5. Connector architecture

Use an adapter interface:

class SourceConnector(Protocol):
    def discover(self) -> SourceMetadata: ...
    def fetch(self, cursor: str | None = None) -> list[RawRecord]: ...
    def normalize(self, raw: RawRecord) -> FinancialRecord: ...

Adapters:

CSV/XLSX/PDF adapters       ← MVP
Plaid connector             ← bank/account feeds
Stripe connector            ← payments/settlements
Accounting connector        ← ERP/accounting software
Credit account connector    ← card/credit feeds
Custom connector            ← business-specific source

All adapters terminate in the canonical data model.

6. Plaid and Stripe sandboxes

Sandboxes should be used as integration-test environments, not as the only demo data source.

Plaid Sandbox supports API and Link testing, test Items, configurable/custom test data, transaction simulation, and Sandbox-only webhook triggers. Plaid also exposes /sandbox/transactions/create for adding custom transactions to a Sandbox Item. citeturn136401search2turn136401search3turn136401search5

Stripe Sandboxes are isolated environments for testing payment behavior without real money movement and can be used to create/test payments and simulated events. citeturn136401search4

Recommended architecture:

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

The deterministic benchmark remains the authoritative evaluation source because it has exact ground truth.

7. Reconciliation engine

The engine should support multiple reconciliation templates.

7.1 Bank reconciliation

Bank transactions ↔ GL / cash ledger

Rules include:

exact reference match;

exact amount/date match;

tolerance windows;

known outstanding items;

fee relationships;

timing/clearing windows;

one-to-many and many-to-one settlements.

7.2 Vendor reconciliation

PO ↔ Invoice ↔ AP ledger ↔ Payment ↔ Bank

Supports:

2-way/3-way matching;

partial invoices;

partial payments;

duplicate invoices;

overpayment/underpayment;

invoice/payment allocation.

7.3 Customer reconciliation

Invoice ↔ Receipt ↔ Processor ↔ Bank ↔ AR ledger

Supports:

partial payment;

split payment;

remittance references;

refunds/chargebacks;

unapplied cash.

7.4 Business-specific reconciliation

Define a source graph:

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

Each edge can specify matching fields, date windows, amount tolerances, and cardinality.

8. Three-stage matching architecture

Stage A — deterministic matching

Fast, explainable, no LLM.

Examples:

exact invoice ID
exact payment ID
exact settlement ID
exact reference
exact amount + currency
known processor fee formula
allowed timing window

Every rule should emit a reason code:

MATCH_EXACT_REFERENCE
MATCH_EXACT_AMOUNT_DATE
MATCH_KNOWN_SETTLEMENT_PATTERN
MATCH_FEE_VARIANCE
MATCH_TIMING_WINDOW

Stage B — graph/path matching

This is not necessarily “trained”. It is an algorithmic search/optimization layer.

Represent records as a graph:

Invoice ──paid_by──► Payment
Payment ──processed_by──► ProcessorEvent
ProcessorEvent ──included_in──► SettlementBatch
SettlementBatch ──deposited_as──► BankTxn
BankTxn ──posted_as──► GLEntry

Support many-to-one and one-to-many paths.

Candidate graph construction

create entities/nodes;

create deterministic candidate edges using blocking keys;

score edge compatibility using amount/date/reference/party constraints;

enumerate small candidate paths;

solve for a consistent subgraph subject to conservation and cardinality constraints.

Possible algorithms:

bipartite matching for pairwise reconciliation;

min-cost flow for one-to-many/many-to-one allocation;

beam search over candidate paths for multi-hop lineage;

connected-component analysis for duplicate/split groups;

constraint solving for amount conservation.

For a payment-to-bank example:

Payment = 1000
Fee = 30
FX = 5
Expected settlement = 965
Bank deposit = 965

The path is valid even though no single row equals the original payment amount.

Stage C — ML scoring

Use ML for ambiguous candidate ranking, not basic accounting arithmetic.

Feature groups:

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
  description embedding similarity

entity:
  vendor/customer match
  account match
  historical relationship frequency

graph:
  path length
  path reliability
  number of supporting records

Initial model: gradient-boosted tree or logistic regression baseline. Move to a learned ranking model only if benchmark results justify it.

Output:

{
  "candidate_id": "cand_123",
  "match_probability": 0.982,
  "feature_summary": {...}
}

9. How to train the ML matcher

Use the synthetic datasets as supervised training/evaluation material, but prevent leakage.

9.1 Training examples

Construct positive and negative pairs/groups from known ground truth.

Positive:

payment P ↔ settlement S

Negative:

P ↔ unrelated settlement

Hard negatives:

same amount, wrong date;

same vendor, wrong invoice;

correct invoice but wrong settlement;

legitimate timing difference;

valid split payment;

fee-related amount difference.

9.2 Split strategy

Never randomly split individual rows from the same generated world into train and test if this leaks templates.

Prefer:

generator seeds
scenario IDs
failure categories
entities
months

held out by group.

Example:

Train: seeds 1–30
Validation: seeds 31–35
Test: seeds 36–40

Then create a second harder test set with unseen combinations of failure types.

9.3 Training pipeline

ReconRiver / FinRCA / custom generated cases
             ↓
       candidate generator
             ↓
        feature builder
             ↓
      train / validation split
             ↓
           model fit
             ↓
       calibration / threshold
             ↓
       held-out evaluation
             ↓
      model artifact + version

Log model version, features, seed, dataset hash, threshold, and metrics.

9.4 Thresholding

Do not select the threshold solely for F1.

Select thresholds for:

high-precision auto-match;

medium-confidence candidate queue;

low-confidence exception investigation.

For example:

P(match) >= 0.995   → eligible for automatic action
0.90–0.995          → candidate/secondary validation
< 0.90              → unresolved / investigation

These are starting values, not final production thresholds; tune them on held-out data.

10. Ground-truth datasets and how each is used

10.1 ReconRiver

ReconRiver is the primary operational reconciliation benchmark. It is deterministic and synthetic, with canonical payments leading into an internal ledger, processor events, bank settlements, and expected reconciliation ground truth. It provides clean-settlement, mixed-exceptions, month-end-close, and failure-recovery scenario packs, including 1K and 10K-scale cases. citeturn136401search0

Use it for:

deterministic matcher validation;

graph/path reconciliation;

exception taxonomy;

end-to-end reconciliation accuracy;

scale/performance tests;

failure recovery/idempotency tests.

10.2 FinRCA-AI-Bench

FinRCA is a deterministic synthetic benchmark focused on financial reconciliation and root-cause analysis. It includes tables such as vendors, POs, invoices, payments, allocations, GL entries, bank transactions/statements, approvals and audit logs; its generated benchmark covers multiple failure categories and legitimate/no-failure cases. citeturn136401search7

Use it for:

exception detection;

root-cause classification;

evidence retrieval;

proposed resolution correctness;

hard-negative evaluation.

10.3 FinBalance

FinBalance contains document/OCR text, rendered PDF-style assets, trial balances, account taxonomies, expected journal entries, final balance sheets, contradiction labels, and multi-document accounting scenarios across several industries and complexity levels. It can also generate fresh datasets. citeturn136401search8

Use it for:

PDF/document ingestion;

accounting-document understanding;

multi-document evidence grounding;

journal-entry validation;

contradiction detection;

document parser evaluation.

10.4 Custom benchmark

Build a small project-specific suite combining:

clean matches
fee variance
timing difference
duplicate
partial payment
split settlement
missing bank item
missing ERP item
wrong allocation
wrong period
ambiguous remittance
messy PDF table
scanned PDF
hard negative

Every custom case must have exact ground truth.

11. Investigation agent architecture

The investigation agent is bounded and evidence-driven.

It is not called for every transaction.

Trigger condition:

unresolved after deterministic
AND
unresolved/low-confidence after graph + ML

Input case

{
  "case_id": "EX-8291",
  "exception_type": "AMOUNT_MISMATCH",
  "candidate_records": [...],
  "computed_variance": 260.00,
  "currency": "USD",
  "reconciliation_policy": {...}
}

Agent tool set

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

Investigation loop

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

Token-control design

Enforce:

max tool calls per case;

maximum evidence rows per call;

maximum context bytes/tokens;

no repeated identical searches;

structured tool results rather than raw database dumps;

early stop once sufficient evidence is found;

deterministic calculations outside the LLM;

evidence bundle deduplication.

Example policy:

max_llm_turns = 4
max_tool_calls = 8
max_evidence_records = 30

Adjust from evaluation rather than hard-code blindly.

The goal is not “let the agent reason until it is happy”; it is “retrieve the minimum evidence needed to close the case.”

12. LLM usage architecture

GLM-4-7B-Flash MoE 30B should be the single available reasoning model behind TensorMux.

Use cases:

A. Extraction fallback

Only when deterministic/OCR/table parsing confidence is insufficient.

Input:

cropped table/page;

extracted tokens/cells;

schema target;

nearby headings/footnotes.

Output strict JSON.

B. Exception investigation

Only unresolved cases.

Input = compact evidence bundle, not source database.

C. Summary generation

Use already-computed structured metrics.

The LLM should not calculate KPI values; it verbalizes known values.

D. Review explanation

Convert evidence + validated decision into clear reviewer language.

13. AO application-agent design

Runtime application agents:

Recon Controller
 ├── Investigation Agent
 ├── Document Extraction Agent
 ├── Summary Agent
 └── Review Explanation Agent

Use a single controller workflow where possible. Specialist agents should be invoked as bounded capabilities, not as free-form autonomous agents.

AO at aoagents.dev is used separately by the development team to supervise multiple coding agents working in isolated workspaces/branches and connecting them to GitHub, CI, PRs and reviews. citeturn136401search1

14. Runtime workflow state machine

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

Every transition is persisted and idempotent.

15. Accounting validator

Before any write/action:

amount arithmetic correct?
Debit = credit?
currency valid?
period valid?
duplicate action?
existing reconciliation?
source records still valid?
policy allows action?

LLM-generated journal entries are proposals only.

All final journal entries are generated/validated by deterministic code.

16. Approval policy engine

Policy is code/configuration, not a prompt.

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

Policy output:

{
  "decision": "HUMAN_REVIEW",
  "reason_codes": ["HIGH_VALUE", "NON_STANDARD_VARIANCE"],
  "required_evidence": ["bank_txn", "settlement", "invoice"]
}

17. Database architecture

Use PostgreSQL as the primary system of record.

Recommended tables:

organizations
source_systems
financial_accounts
parties

raw_documents
document_pages
document_regions
extracted_tables
extracted_cells

invoices
purchase_orders
payments
settlements
bank_transactions
ledger_entries
processor_events

reconciliation_runs
reconciliation_items
match_candidates
match_decisions

exception_cases
investigations
evidence_items
proposed_actions
approvals
journal_entries

audit_events
agent_runs
model_calls

Object storage holds source PDFs/XLSX/CSV and page/table images. PostgreSQL stores metadata, normalized records, provenance and workflow state.

For the graph, start with relational adjacency tables:

entity_nodes
entity_edges
candidate_edges

Do not introduce a graph database in the MVP.

Redis/background queue is optional. For the MVP, FastAPI background jobs or a simple worker queue can run ingestion/reconciliation. Introduce Redis/Celery/RQ only when concurrency requires it.

18. API contracts

Upload

POST /api/documents/upload

Ingestion status

GET /api/documents/{document_id}
GET /api/documents/{document_id}/preview

Start reconciliation

POST /api/reconciliation/runs

Body:

{
  "type": "bank",
  "source_ids": ["bank_1", "ledger_1"],
  "period": {"start": "2026-01-01", "end": "2026-01-31"}
}

Results

GET /api/reconciliation/runs/{run_id}
GET /api/reconciliation/runs/{run_id}/items
GET /api/reconciliation/runs/{run_id}/exceptions

Investigation

POST /api/exceptions/{exception_id}/investigate
GET  /api/exceptions/{exception_id}/investigation

Review

POST /api/exceptions/{exception_id}/approve
POST /api/exceptions/{exception_id}/reject
POST /api/exceptions/{exception_id}/escalate

Reports

GET /api/reports/reconciliation/{run_id}
GET /api/reports/exceptions/{run_id}
GET /api/reports/audit/{run_id}

All APIs return machine-readable IDs/statuses; frontend rendering is separate.

19. TensorMux placement

TensorMux is the model inference gateway, not the workflow engine. Its documented gateway supports a single OpenAI-compatible endpoint and routes requests to configured inference backends. citeturn595120search3

Architecture:

AO application agent
        ↓
OpenAI-compatible client
        ↓
TensorMux
        ↓
GLM-4-7B-Flash MoE 30B

Keep provider/model selection behind configuration.

Expose model-call telemetry:

model
prompt_tokens
completion_tokens
latency_ms
retry_count
status
estimated_cost
case_id
agent_run_id

Even with one available model, the gateway gives us one stable inference boundary and makes later model routing possible without changing application agent code.

20. Neatlogs / observability

Trace:

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

Store a local minimal agent_runs record regardless of external observability availability.

Track:

total run time;

deterministic matching time;

graph matching time;

ML inference time;

agent time;

tool-call count;

model tokens;

model latency;

failure/retry counts;

final decision.

21. Frontend technical architecture

Next.js App Router + TypeScript.

Core routes:

/dashboard
/reconciliation
/reconciliation/[id]
/exceptions
/exceptions/[id]
/documents
/documents/[id]
/reports
/settings/integrations

Components:

UploadDropzone
DocumentProcessingStatus
ReconciliationTable
MatchBadge
ExceptionQueue
EvidencePanel
TransactionGraph
InvestigationTimeline
ApprovalPanel
ReportCharts
AgentTracePanel

Use a professional finance visual system inspired by Maximor’s restrained enterprise-finance feel: neutral surfaces, compact data-dense tables, deliberate accent color, strong hierarchy, and clear states. UFO-style/graph visualization is used selectively for lineage and agent execution rather than as the entire visual language.

Frontend state:

TanStack Query for server state;

local component state for transient UI;

typed API client generated from OpenAPI.

Charts:

reconciliation progress;

exception composition;

amount-at-risk;

automation rate;

aging of unresolved items;

performance/evaluation metrics.

22. Reporting architecture

Reports should be generated primarily from SQL/structured state, not by LLM.

Report pipeline:

Postgres metrics
   ↓
metric computation
   ↓
report JSON
   ↓
Next.js charts/tables
   ↓
optional LLM narrative summary

Report types:

reconciliation summary;

exceptions by root cause;

unresolved/approval queue;

amount at risk;

evidence coverage;

audit history;

agent performance.

23. Idempotency and failure recovery

Every external/import operation gets an idempotency key:

source_system + source_record_id + source_version

Do not duplicate records when a job restarts.

Reconciliation run state must support restart:

checkpoint → resume → preserve completed matches → continue unresolved work

ReconRiver’s failure-recovery scenarios should be used to validate this behavior. citeturn136401search0

24. Evaluation architecture

Three primary benchmark loops:

Matching benchmark

Measures:

pairwise match precision/recall;

one-to-many allocation accuracy;

false match rate;

unmatched recall.

Exception/RCA benchmark

Measures:

exception detection precision/recall;

root cause accuracy;

evidence precision/recall;

resolution accuracy;

hard-negative false-positive rate.

End-to-end benchmark

Measures:

complete reconciliation accuracy;

auto-resolution precision;

human-review routing accuracy;

financial exposure of incorrect autonomous actions;

workflow completion rate.

FinRCA’s explicit root-cause/evidence/resolution structure and legitimate/no-failure cases should be used to make these metrics meaningful. citeturn136401search7

25. Financial-risk metrics

Do not report only classification accuracy.

Compute:

Auto-approval precision
Auto-approval recall
Human-routing precision
False-positive financial exposure
False-negative financial exposure
Amount correctly reconciled
Automation rate

Example:

financial_false_positive_exposure
= sum(amount of incorrectly auto-resolved cases)

This should be one of the headline metrics.

26. Accuracy / reliability / cost / speed experiment

Compare at minimum:

Baseline A

Deterministic-only matcher.

Baseline B

Deterministic + graph + ML.

System C

Deterministic + graph + ML + bounded GLM investigation.

Optionally:

System D

Same as C with tighter evidence selection/tool-call limits.

Record:

accuracy
RCA accuracy
hard-negative FP rate
financial exposure
latency
LLM calls/case
tokens/case
cost/case
failure rate

This demonstrates whether the agentic layer creates measurable value rather than merely increasing complexity.

27. Training/evaluation data flow

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
      TRAINING                 TESTING
          │                        │
    ML matcher             End-to-end agent
          │                        │
          ▼                        ▼
       artifact                 metrics

Do not use test-set labels as prompts or retrieval documents.

28. Security boundaries for MVP

No production authentication stack is required for the hackathon.

Still enforce:

secrets only in environment variables;

uploaded files stored outside source control;

sandbox credentials isolated;

source provenance on every imported record;

no raw credentials in agent context;

no unrestricted SQL tool for agents;

tool allowlists;

structured write endpoints;

audit log for every mutation.

29. Deployment architecture

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

TensorMux → model inference endpoint
Neatlogs  → observability

Use GitHub CI for:

type checks;

Python tests;

frontend tests;

linting;

API schema validation;

evaluation smoke tests.

30. Technical build sequence

The implementation order should be:

canonical schemas;

database/migrations;

upload/object storage;

CSV/XLSX ingestion;

PDF/table extraction;

deterministic reconciliation;

graph/path matcher;

ML candidate scorer;

evaluation harness;

AO runtime agent integration;

TensorMux/GLM integration;

evidence/reasoning tools;

policy/approval engine;

reports/audit;

frontend integration;

Plaid/Stripe adapters;

performance/reliability benchmark;

final demo instrumentation.

The detailed parallel coding-agent breakdown for this sequence is in