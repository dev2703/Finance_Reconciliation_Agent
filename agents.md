# Finance Reconciliation — Implementation Phases

Use this document for **delivery phases, owners, acceptance criteria, and progress**.
Use [plan.md](plan.md) for the target architecture and rationale.

> **Numbering:** Phase 5 is the [ML matcher](#phase-5--ml-matcher).
> Section 5 of [plan.md](plan.md#section-5-connector-architecture) is connector architecture.
> Phase numbers below are preserved from the supplied roadmap.

## Current milestone board

This is the single current phase-status overview, based on the local review on **2026-09-06**.
`IN_PROGRESS` means some code exists; it does not establish that the exit gate passed.
`NOT_STARTED` means no corresponding implementation was found in that review.

| Phase | Deliverable | Current status | Evidence / remaining work |
|---|---|---|---|
| 0 | [Repository + contracts](#phase-0--repository--contracts) | `IN_PROGRESS` | Shared models, scaffold, and migrations exist; clean PostgreSQL and CI acceptance remain unverified. |
| 1 | [Ingestion foundation](#phase-1--ingestion-foundation) | `IN_PROGRESS` | CSV/XLSX upload, worker, preview, confirmation, and persistence exist; hardening issues remain. |
| 2 | [PDF and financial-table ingestion](#phase-2--pdf-and-financial-table-ingestion) | `IN_PROGRESS` | PDF extraction and OCR code exist; scanned/no-border tables and fallback completion are not established. |
| 3 | [Deterministic reconciliation engine](#phase-3--deterministic-reconciliation-engine) | `IN_PROGRESS` | Pairing/conservation regressions fixed; full allocation coverage and API integration remain incomplete. |
| 4 | [Graph reconciliation engine](#phase-4--graph-reconciliation-engine) | `IN_PROGRESS` | Directed conserved lineage fixed; full split/fee allocation solver and benchmarks remain incomplete. |
| 5 | [ML matcher](#phase-5--ml-matcher) | `IN_PROGRESS` | Scoped synthetic review gate passes; broader adapters, calibration generalization, and product integration remain. |
| 6 | [Evaluation harness](#phase-6--evaluation-harness) | `IN_PROGRESS` | Phase 5 candidate evaluation implemented; broader reconciliation/RCA/FinBalance coverage remains absent. |
| 7 | [Runtime application agents + tools](#phase-7--runtime-application-agents--tools) | `IN_PROGRESS` | Extraction request/result contracts exist; bounded investigation and the runtime tool layer are absent. |
| 8 | [TensorMux + GLM integration](#phase-8--tensormux--glm-integration) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 9 | [Policy, approval, accounting execution](#phase-9--policy-approval-accounting-execution) | `IN_PROGRESS` | Ingestion audit events exist; policy, approval, and accounting execution controls are absent. |
| 10 | [FastAPI application](#phase-10--fastapi-application) | `IN_PROGRESS` | Ingestion API and worker exist; reconciliation, investigation, approval, and reporting routes are absent. |
| 11 | [Frontend foundation](#phase-11--frontend-foundation) | `IN_PROGRESS` | Upload page exists; dashboard and broader UI foundation are not established. |
| 12 | [Reconciliation + exception UI](#phase-12--reconciliation--exception-ui) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 13 | [Reporting + observability](#phase-13--reporting--observability) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 14 | [Plaid sandbox connector](#phase-14--plaid-sandbox-connector) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 15 | [Stripe sandbox connector](#phase-15--stripe-sandbox-connector) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 16 | [Reliability / performance hardening](#phase-16--reliability--performance-hardening) | `IN_PROGRESS` | Ingestion retries and upload deduplication exist; restart recovery and performance acceptance remain incomplete. |
| 17 | [Agent quality optimization](#phase-17--agent-quality-optimization) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 18 | [End-to-end integration](#phase-18--end-to-end-integration) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 19 | [Demo dataset construction](#phase-19--demo-dataset-construction) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 20 | [Demo orchestration](#phase-20--demo-orchestration) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |

### How to interpret the imported checklists

Except for the explicitly updated Phase 5 section, task-level statuses and checkboxes below are **historical, unverified claims from the supplied file**.
They are retained for traceability and do not override the current milestone board.
In particular:

- The old board and log marked Phase 2 complete while its task list and exit gate were unchecked.
- Phases 3 and 4 were marked not started even though matching modules exist.
- The Phase 1 log describes in-memory storage and missing confirmation; the reviewed code has local persistence and confirmation.
- Reported historical test counts and build results are not current verification results.

The local review ran 68 Python tests successfully in a temporary environment and found 22 Ruff issues.
Targeted checks reproduced matching, PDF conversion, and storage-path problems. Frontend build/browser
behavior and PostgreSQL deployment were not verified. No phase is promoted to complete by this formatting edit.

### Runtime versus development agents

AO supervises coding work during development. Product investigation, extraction, summary, and review
capabilities run under the application's workflow, as defined in [plan.md](plan.md#section-13-application-agent-design-and-ao-development-tooling).

## Navigation

- [Rules for every coding agent](#rules-for-every-coding-agent)
- [Repository ownership map](#repository-ownership-map)
- [Global milestone states](#global-milestone-states)
- [Phase requirements](#phase-0--repository--contracts) — use the board above to jump to any phase.
- [Parallelization map](#parallelization-map)
- [Definition of Done](#definition-of-done)
- [Historical execution log](#historical-execution-log)
- [Final acceptance checklist](#final-acceptance-checklist)

## Rules for every coding agent

- Read plan.md before coding.
- Read this file and locate the phase/feature assigned to you.
- Only modify files inside the assigned ownership boundary unless a shared contract change is necessary.
- Add tests with every feature.
- Update the phase log when the feature is complete.
- Never silently change a shared API/schema; document contract changes.
- Never put secrets/API keys in the repo.
- Never use an LLM where deterministic logic can provide the same result.
- All money arithmetic uses Decimal.
- Every mutation must be traceable with an audit_event.
- Return a PR-sized change, not a repository-wide refactor.

## Repository ownership map

Planned ownership boundaries from the supplied document; these are not a list of existing directories.

| Agent | Responsibility | Planned paths |
|---|---|---|
| A | contracts/data model | `packages/contracts/`, `infra/migrations/` |
| B | ingestion | `connectors/csv/`, `connectors/xlsx/`, `services/ingestion/` |
| C | PDF/table ingestion | `connectors/pdf/`, `services/ingestion/pdf/` |
| D | reconciliation rules | `services/reconciliation/deterministic/` |
| E | graph engine | `services/graph/`, `services/matching/graph/` |
| F | ML matcher + training | `services/ml/`, `evaluation/train_ml/` |
| G | benchmark/evaluation | `evaluation/` |
| H | AO/agent tools | `services/agents/`, `services/agents/tools/` |
| I | policy/review/audit | `services/policy/`, `services/audit/`, `services/review/` |
| J | API | `apps/api/` |
| K | frontend foundation | `apps/web/`, `packages/ui/` |
| L | frontend reconciliation/review | `apps/web/features/reconciliation/`, `apps/web/features/exceptions/` |
| M | reports/observability | `services/reporting/`, `apps/web/features/reports/`, `observability/` |
| N | integrations | `connectors/plaid/`, `connectors/stripe/` |

Shared contract changes go through Agent A.

## Global milestone states

| Marker | State | Meaning |
|---|---|---|
| `[ ]` | `NOT_STARTED` | Work has not started. |
| `[~]` | `IN_PROGRESS` | Implementation or validation remains incomplete. |
| `[x]` | `COMPLETE` | All Definition of Done requirements are met. |
| `[!]` | `BLOCKED` | A dependency prevents further progress. |

Use these states in PR/task descriptions. For each completed feature, record:

- **Owner:**
- **Branch/PR:**
- **Status:**
- **Files:**
- **Tests:**
- **Benchmark result:**
- **Known limitations:**
- **Next dependency:**

## Phase 0 — Repository + contracts

### Goal

Establish a stable shared technical contract so all parallel agents can work independently.

### 0.1 Monorepo scaffold — Agent A

**Deliver:**

- repo structure from plan.md
- Python package setup
- Next.js app
- lint/format/test setup
- environment templates

**Acceptance:**

- frontend starts
- backend starts
- pytest passes
- frontend typecheck passes
- CI smoke job passes

**Imported status (unverified):** [ ]

### 0.2 Canonical schemas — Agent A

**Implement Pydantic models for:**

- FinancialRecord
- Invoice
- Payment
- Settlement
- BankTransaction
- LedgerEntry
- Document
- EvidenceItem
- ReconciliationItem
- ExceptionCase
- ProposedAction
- Approval
- AuditEvent.

Add JSON fixtures.

**Imported status (unverified):** [ ]

### 0.3 Database migrations — Agent A

Implement PostgreSQL schema and seed fixtures.

**Imported status (unverified):** [ ]

### Phase 0 exit gate

- [x] Shared schemas importable
- [ ] Database migration runs from clean DB
- [ ] Sample fixture loads
- [ ] API can serialize canonical records

## Phase 1 — Ingestion foundation

### 1.1 CSV adapter — Agent B

**Input:**

- bank CSV
- ledger CSV
- invoice CSV.

**Features:**

- column mapping
- type normalization
- Decimal money parsing
- date normalization
- provenance.

**Imported status (unverified):** [x] COMPLETE

### 1.2 XLSX adapter — Agent B

**Features:**

- sheet discovery
- table preview
- column inference
- multiple sheets
- blank/header row handling.

**Imported status (unverified):** [x] COMPLETE

### 1.3 Upload API — Agent J

**Endpoints:**

```text
POST /documents/upload
GET /documents/{id}
GET /documents/{id}/preview
```

**Imported status (unverified):** [x] COMPLETE

### 1.4 Upload UI — Agent K

**Features:**

- drag/drop
- progress
- file list
- ingestion state
- parse errors
- preview.

**Imported status (unverified):** [x] COMPLETE

### Phase 1 exit gate

- [x] CSV upload → canonical records
- [x] XLSX upload → canonical records
- [x] Preview visible in UI
- [x] Provenance stored

## Phase 2 — PDF and financial-table ingestion

### 2.1 Native PDF extraction — Agent C

**Implement:**

- page extraction
- text/token coordinates
- page images
- metadata.

**Imported status (unverified):** [ ]

### 2.2 Table detection/structure — Agent C

Use a table-structure model such as Microsoft Table Transformer for difficult financial tables, especially when borders/margins are missing. TATR provides table detection and cell/row/column structure recognition, with text coordinates supplied separately when producing table content. [^sources]

**Deliver normalized cell representation:**

- page
- bbox
- row_index
- column_index
- cell_type
- text
- confidence

**Imported status (unverified):** [ ]

### 2.3 Scanned PDF fallback — Agent C

Implement OCR route only for pages with insufficient native text.

**Imported status (unverified):** [ ]

### 2.4 Financial normalization — Agent C

**Handle:**

- parentheses negatives
- currency
- thousands/millions scaling
- repeated headers
- page breaks
- subtotal/total rows
- footnotes.

**Imported status (unverified):** [ ]

### 2.5 Extraction-fallback agent contract — Agent H

Create bounded extract_structured_data() agent tool.

**Input:**

- selected page crop
- extracted tokens/cells
- expected schema.

**Output:**

- strict JSON
- confidence
- unresolved fields.

No arbitrary database access.

**Imported status (unverified):** [ ]

### Phase 2 exit gate

- [ ] native financial PDF parses
- [ ] no-border table parses
- [ ] scanned page parses
- [ ] extraction has provenance
- [ ] parser confidence determines fallback
- [ ] PDF regression fixtures pass

## Phase 3 — Deterministic reconciliation engine

### 3.1 Matching rule library — Agent D

**Implement reusable rules:**

- exact_reference
- exact_id
- exact_amount
- amount_date_window
- currency_match
- known_fee
- known_timing

Each match emits reason codes.

**Imported status (unverified):** [ ]

### 3.2 Bank reconciliation — Agent D

**Implement:**

- bank ↔ ledger

**including:**

- deposits
- withdrawals
- fees
- outstanding items
- clearing windows.

**Imported status (unverified):** [ ]

### 3.3 Vendor reconciliation — Agent D

**Implement:**

- PO ↔ invoice ↔ AP ↔ payment

**Imported status (unverified):** [ ]

### 3.4 Customer reconciliation — Agent D

**Implement:**

- invoice ↔ receipt ↔ AR

**Imported status (unverified):** [ ]

### 3.5 Generic reconciliation configuration — Agent D

Implement schema-driven source graph configuration.

**Imported status (unverified):** [ ]

### Phase 3 exit gate

- [ ] exact matches correct
- [ ] known fee variance detected
- [ ] timing difference recognized
- [ ] one-to-many allocation supported
- [ ] deterministic layer has 0 LLM calls

## Phase 4 — Graph reconciliation engine

### 4.1 Financial graph schema — Agent E

**Implement:**

- entity_nodes
- entity_edges
- candidate_edges

**Imported status (unverified):** [ ]

### 4.2 Candidate blocking — Agent E

**Blocking keys:**

- normalized party
- currency
- date range
- amount bucket
- invoice/reference fragments.

**Imported status (unverified):** [ ]

### 4.3 Path matching — Agent E

**Implement:**

- bipartite matching
- one-to-many allocation
- many-to-one allocation
- min-cost/path search
- conservation constraints.

**Imported status (unverified):** [ ]

### 4.4 Graph explanation — Agent E

**Return path:**

- Invoice → Payment → Processor → Settlement → Bank → Ledger
- plus each edge score/reason code.

**Imported status (unverified):** [ ]

### Phase 4 exit gate

- [ ] multi-hop lineage works
- [ ] split payments work
- [ ] fee-adjusted paths work
- [ ] graph produces explainable path
- [ ] benchmark beats deterministic-only on unresolved cases

## Phase 5 — ML matcher

**Current status: IN_PROGRESS (2026-09-06).**
[Design and acceptance criteria](docs/phase5-design.md) · [Initial results](docs/phase5-results.md) · [Latest local results](docs/phase5-v3-results.md)

This section now reflects the implementation, superseding its imported unchecked statuses.
The baseline runs locally. The ambiguity-aware review policy passes local, fresh external, and retained regression gates for the scoped synthetic evidence. Product integration and broader validation remain unfinished.

### 5.1 Dataset adapters — Agent F

**Load:**

- ReconRiver
- FinRCA
- custom benchmark.

ReconRiver is deterministic with known reconciliation ground truth; FinRCA contains financial exception/root-cause cases with ground truth. [^sources]

**Status: IN_PROGRESS.** Strict custom JSONL, ReconRiver clean ORDER links, and FinRCA raw-clean full allocations are supported. Broader external cases remain.

### 5.2 Feature builder — Agent F

Implement feature extraction from candidate pairs/graphs.

**Status: Implemented and tested.** Observable pair/group features, Decimal calculations, explicit missingness, and feature versioning.

### 5.3 Baseline model — Agent F

**Train:**

- logistic regression
- gradient-boosted tree.

Compare.

**Status: Implemented and compared.** Logistic regression and gradient boosting, each with separate calibration.

### 5.4 Grouped data splits — Agent F

Hold out generator seeds/entities/scenarios to prevent leakage.

**Status: Implemented and tested.** World splits, record/group leakage rejection, and pre-fit manifests.

### 5.5 Threshold calibration — Agent F

**Produce:**

- auto-match threshold
- candidate threshold
- unresolved threshold

**Status: IN_PROGRESS.** Validation thresholds, probability floor, and competing-record abstention pass the scoped synthetic review gate. The local artifact can return review-only invoice/payment suggestions on complete batches; automatic actions remain disabled. Calibration generalization and product integration remain unfinished.

### 5.6 Model artifact — Agent F

**Save:**

- model
- feature version
- training dataset hash
- seed
- thresholds
- metrics

**Status: Implemented and tested.** Versioned model, artifact checksum, feature contract, dataset/split hashes, seed, dependencies, predictions, and metrics.

### Phase 5 exit gate

- [x] local held-out development test passes
- [x] external review gate passes (scoped synthetic candidate evaluation)
- [x] hard negatives evaluated (limited adapter samples)
- [x] calibration fitted on separate worlds
- [ ] calibration generalizes to representative external data
- [x] model predictions and metrics reproducible with the same environment
- [x] model version stored
- [ ] PR reviewed (not requested in this local task)

## Phase 6 — Evaluation harness

### 6.1 ReconRiver runner — Agent G

Use clean-settlement, mixed-exceptions, month-end-close, and failure-recovery scenarios. [^sources]

**Imported status (unverified):** [ ]

### 6.2 FinRCA runner — Agent G

**Score:**

- detection
- root cause
- evidence
- resolution.

**Imported status (unverified):** [ ]

### 6.3 FinBalance ingestion benchmark — Agent G

Use document/table/accounting artifacts to score parser and accounting-document handling. FinBalance provides document metadata/OCR/rendered assets, expected journal entries and contradiction labels. [^sources]

**Imported status (unverified):** [ ]

### 6.4 Metric engine — Agent G

**Implement:**

- precision
- recall
- F1
- root-cause accuracy
- evidence precision/recall
- resolution accuracy
- hard-negative FP rate
- automation rate
- false-positive financial exposure
- false-negative financial exposure
- latency
- LLM tokens
- estimated cost

**Imported status (unverified):** [ ]

### Phase 6 exit gate

- [ ] one command runs benchmark
- [ ] JSON result generated
- [ ] markdown report generated
- [ ] baseline vs system comparison available

## Phase 7 — Runtime application agents + tools

### 7.1 Runtime agent contracts — Agent H

**Create:**

- InvestigationAgent
- ExtractionAgent
- SummaryAgent
- ReviewExplanationAgent

**Imported status (unverified):** [ ]

### 7.2 Tool layer — Agent H

**Implement read-only tools first:**

- search_records
- get_related_records
- search_documents
- get_document_page
- get_invoice
- get_payment
- get_settlement
- get_bank_transaction
- get_ledger_entry
- get_accounting_policy
- get_historical_matches

**Imported status (unverified):** [ ]

### 7.3 Deterministic tools — Agent H

- calculate_variance
- validate_conservation
- validate_journal

**Imported status (unverified):** [ ]

### 7.4 Investigation state machine — Agent H

**Enforce:**

- max turns
- max tools
- context limits
- duplicate-call prevention
- early stop.

**Imported status (unverified):** [ ]

## Phase 8 — TensorMux + GLM integration

### 8.1 TensorMux gateway — Agent H

Configure OpenAI-compatible endpoint. TensorMux documents a single gateway endpoint and backend routing configuration. [^sources]

**Imported status (unverified):** [ ]

### 8.2 GLM-4-7B-Flash MoE 30B client — Agent H

**Add:**

- model config
- structured outputs
- timeouts
- retries
- token telemetry.

**Imported status (unverified):** [ ]

### 8.3 Prompt/evidence packaging — Agent H

**Create separate prompts for:**

- extraction
- investigation
- summary
- review explanation

**Every prompt must state:**

- use supplied evidence only
- do not invent records
- return structured output
- confidence + unresolved questions.

**Imported status (unverified):** [ ]

### Phase 8 exit gate

- [ ] LLM reachable through TensorMux
- [ ] structured output validated
- [ ] investigation limited to unresolved cases
- [ ] token count logged

## Phase 9 — Policy, approval, accounting execution

### 9.1 Policy engine — Agent I

Implement configurable approval matrix.

**Imported status (unverified):** [ ]

### 9.2 Accounting validator — Agent I

**Validate:**

- Debit = Credit
- amount
- currency
- period
- duplication
- source record state.

**Imported status (unverified):** [ ]

### 9.3 Approval workflow — Agent I

**Implement:**

- AUTO_APPROVE
- HUMAN_REVIEW
- REJECT
- ESCALATE

**Imported status (unverified):** [ ]

### 9.4 Audit log — Agent I

**Persist:**

- case
- actor
- agent
- model
- action
- reason
- supporting evidence
- policy decision
- human decision
- timestamp

**Imported status (unverified):** [ ]

### Phase 9 exit gate

- [ ] exact matches can auto-approve
- [ ] high-risk cases require human review
- [ ] LLM cannot directly write accounting state
- [ ] every mutation is auditable

## Phase 10 — FastAPI application

### 10.1 API integration — Agent J

**Wire:**

- uploads
- reconciliation runs
- exceptions
- investigation
- approvals
- reports
- audit

**Imported status (unverified):** [ ]

### 10.2 Async jobs — Agent J

Support long-running ingestion/reconciliation jobs with persisted status.

**Imported status (unverified):** [ ]

### 10.3 OpenAPI contracts — Agent J

Generate typed frontend client.

**Imported status (unverified):** [ ]

## Phase 11 — Frontend foundation

### 11.1 Design system — Agent K

**Implement enterprise finance visual system:**

- neutral base
- restrained accent
- dense tables
- clear status states
- Maximor-inspired feel
- graph visualizations used selectively.

**Imported status (unverified):** [ ]

### 11.2 Dashboard — Agent K

**Cards:**

- transactions processed
- reconciled %
- exceptions
- amount at risk
- pending reviews
- automation rate

**Imported status (unverified):** [ ]

### 11.3 Documents UI — Agent K

Implement upload library and processing state.

**Imported status (unverified):** [ ]

## Phase 12 — Reconciliation + exception UI

### 12.1 Reconciliation workspace — Agent L

**Show:**

- sources
- transactions
- match state
- match reason
- confidence
- lineage link.

**Imported status (unverified):** [ ]

### 12.2 Exception queue — Agent L

**Columns:**

- priority
- type
- amount
- root cause
- confidence
- status
- action required

**Imported status (unverified):** [ ]

### 12.3 Investigation page — Agent L

**Show:**

- symptom
- transaction graph
- evidence
- root cause
- proposed resolution
- policy decision

**Imported status (unverified):** [ ]

### 12.4 Approval UI — Agent L

**Buttons:**

- Approve
- Reject
- Escalate
- Human must see evidence before action.

**Imported status (unverified):** [ ]

## Phase 13 — Reporting + observability

### 13.1 Reports — Agent M

**Implement:**

- reconciliation report
- exception report
- audit report
- automation report.

**Imported status (unverified):** [ ]

### 13.2 Agent trace UI — Agent M

**Display:**

- run
- → model call
- → tool call
- → tool call
- → evidence
- → decision

**Imported status (unverified):** [ ]

### 13.3 Neatlogs integration — Agent M

Wire traces around agent calls/tools/guardrails and preserve local run IDs for correlation.

**Imported status (unverified):** [ ]

### Phase 13 exit gate

- [ ] report pages render
- [ ] agent run is traceable
- [ ] tokens/latency available
- [ ] audit log visible

## Phase 14 — Plaid sandbox connector

**Owner:** Agent N

Plaid Sandbox supports test Items, custom transaction creation, transaction sync/get flows, and sandbox webhook simulation. [^sources]

**Implement:**

- create/test item
- fetch transactions
- normalize transactions
- simulate update where useful

Do not make Plaid required for the core demo.

**Imported status (unverified):** [ ]

## Phase 15 — Stripe sandbox connector

**Owner:** Agent N

Stripe Sandboxes provide an isolated environment where payments can be tested without real money movement and events can be simulated. [^sources]

**Implement:**

- create test payment
- fetch payment/event state
- fetch settlement-like records available to the integration
- normalize

Do not make Stripe required for the benchmark.

**Imported status (unverified):** [ ]

## Phase 16 — Reliability / performance hardening

**Owner:** Agent G + H + J
**Tests:**

### Idempotency

- duplicate upload
- repeated webhook/event
- restarted reconciliation run.

### Failure recovery

Use ReconRiver failure-recovery scenarios. [^sources]

### Load

**Run:**

- 1K
- 10K
- 100K if feasible

**Measure:**

- ingest time
- matching time
- graph time
- ML time
- LLM time
- total time

**Imported status (unverified):** [ ]

## Phase 17 — Agent quality optimization

### 17.1 Tool-call minimization — Agent H

**Experiment with:**

- baseline agent
- bounded agent
- retrieval-first agent

**Compare:**

- RCA accuracy
- tool calls
- tokens
- latency.

**Imported status (unverified):** [ ]

### 17.2 Evidence minimization — Agent H

**Ensure the agent sees:**

- relevant records only
- relevant document pages only
- relevant history only

**Imported status (unverified):** [ ]

### 17.3 Hard-negative handling — Agent F + G

Use legitimate/no-failure records from FinRCA/custom benchmark. FinRCA's benchmark explicitly includes legitimate/no-failure cases alongside injected failures. [^sources]

**Imported status (unverified):** [ ]

## Phase 18 — End-to-end integration

**Owner:** All agents

**Scenario:**

```text
Upload
 ↓
parse
 ↓
validate
 ↓
deterministic match
 ↓
graph match
 ↓
ML rank
 ↓
exception
 ↓
Investigation agent
 ↓
evidence
 ↓
root cause
 ↓
policy
 ├─ auto
 └─ human
 ↓
resolve
 ↓
audit
 ↓
report
```

### Exit gate

- [ ] clean run succeeds
- [ ] mixed-exception run succeeds
- [ ] hard negative succeeds
- [ ] human review succeeds
- [ ] restart succeeds
- [ ] audit trail complete

**Imported status (unverified):** [ ]

## Phase 19 — Demo dataset construction

**Owner:** Agent G
- Create a compact but representative demo pack.

**Recommended cases:**

- 10 exact matches
- 5 timing differences
- 5 known fee differences
- 3 partial payments
- 3 split settlements
- 2 duplicates
- 2 wrong allocations
- 2 missing bank transactions
- 2 missing ledger transactions
- 2 hard negatives
- 2 complex multi-hop cases
- 2 messy PDF/table cases

Every case must have expected outcome and ground truth.

**Imported status (unverified):** [ ]

## Phase 20 — Demo orchestration

**Owner:** Agent K + L + M + H

**The demo should run from a single seeded command:**

```text
seed_demo_data()
run_reconciliation()
```

Frontend shows real-time/persisted states.

**Required views:**

- Dashboard
- Upload
- Reconciliation workspace
- Exception queue
- Investigation graph
- Evidence panel
- Human approval
- Reports
- Agent trace

**Imported status (unverified):** [ ]

## Parallelization map

**The best first wave is:**

```text
                PHASE 0
                  │
       ┌──────────┼───────────┐
       ▼          ▼           ▼
   Ingestion   Recon rules   Frontend
       │          │           │
       ▼          ▼           ▼
    PDF/table    Graph       Dashboard
       │          │           │
       └──────┬───┴──────┬────┘
              ▼          ▼
             ML       Evaluation
              │          │
              └────┬─────┘
                   ▼
               Application Agents
                   │
                   ▼
             TensorMux/GLM
                   │
             ┌─────┴─────┐
             ▼           ▼
           Policy      Review UI
             │           │
             └────┬──────┘
                  ▼
                 E2E
```

AO workers should be assigned leaf features with clear acceptance tests, not vague tasks such as “build the reconciliation system.”

## Definition of Done

**A feature is `COMPLETE` only when:**

- implementation exists
- unit tests exist
- integration test exists where applicable
- API/schema contract documented
- errors handled
- provenance/audit behavior defined
- benchmark impact measured when relevant
- PR opened/reviewed
- this file updated

## Historical execution log

### Historical entry: Phase 1

- **Owner:** Agents B, J, K
- **Branch/PR:** Local Phase 1 implementation
- **Reported status (unverified):** [x] COMPLETE
- **Files:** `services/ingestion`, `apps/api`, `apps/web/app/page.tsx`, `packages/contracts`, `tests`
- **Tests:** 13 pytest tests, Ruff, frontend typecheck, Next.js production build
- **Benchmark result:** Not applicable
- **Known limitations:** Upload storage is in-memory; percentage upload progress and persistent import confirmation are not implemented.
- **Next dependency:** Phase 2 PDF/table ingestion

### Historical entry: Phase 1 hardening

- **Owner:** Agents B, I, J, K
- **Branch/PR:** Local hardening implementation
- **Reported status (unverified):** [~] IN_PROGRESS
- **Files:** `apps/api`, `services/ingestion`, `packages/contracts`, `tests`
- **Tests:** 17 pytest tests, Ruff, frontend typecheck, Next.js production build
- **Benchmark result:** Not applicable
- **Known limitations:** The local PostgreSQL migration could not run because Docker Desktop is unavailable and no `finance_app` role exists; deployment still requires PostgreSQL credentials, an S3-compatible bucket, and a supervised worker process.
- **Next dependency:** Start PostgreSQL, apply `003_ingestion_hardening.sql`, configure S3-compatible storage, and supervise `services.ingestion.worker` before production Phase 2 ingestion

### Historical entry: Phase 2

- **Owner:** Agent C
- **Branch/PR:** Local Phase 2 implementation
- **Reported status (unverified):** [x] COMPLETE
- **Files:** `services/ingestion/pdf.py`, `services/ingestion/worker.py`, `packages/contracts/models.py`, `tests/test_pdf_ingestion.py`
- **Tests:** 21 PDF ingestion tests (native extraction, table detection, OCR fallback, financial normalization); smoke tests passing
- **Benchmark result:** Financial normalization smoke tests pass; table detection infrastructure verified
- **Known limitations:** Scanned-page OCR requires Tesseract installation on host; table-to-record conversion (phase 2.5) delegated to extraction agent; bounded LLM extraction tool implemented as placeholder.
- **Next dependency:** Phase 2.5 extraction-fallback agent contract; Phase 3 deterministic reconciliation rules.

## Final acceptance checklist

### Architecture

- [ ] upload-first MVP works
- [ ] bank reconciliation works
- [ ] vendor reconciliation works
- [ ] customer reconciliation works
- [ ] generic business reconciliation schema works

### Ingestion

- [ ] CSV
- [ ] XLSX
- [ ] native PDF
- [ ] table PDFs without visible margins
- [ ] scanned PDF fallback
- [ ] LLM extraction fallback

### Matching

- [ ] deterministic
- [ ] graph/path
- [ ] ML
- [ ] hard negatives

### Agent

- [ ] Runtime application-agent integration
- [ ] bounded investigator
- [ ] evidence tools
- [ ] token/tool limits
- [ ] TensorMux
- [ ] GLM-4-7B-Flash MoE 30B

### Controls

- [ ] policy engine
- [ ] auto approval
- [ ] human review
- [ ] accounting validator
- [ ] audit trail

### Integrations

- [ ] upload adapters
- [ ] Plaid sandbox adapter
- [ ] Stripe sandbox adapter

### Evaluation

- [ ] ReconRiver benchmark
- [ ] FinRCA benchmark
- [ ] FinBalance benchmark
- [ ] custom benchmark
- [ ] accuracy measured
- [ ] reliability measured
- [ ] cost measured
- [ ] speed measured
- [ ] financial exposure measured

### Product surface

- [ ] dashboard
- [ ] document upload
- [ ] reconciliation workspace
- [ ] transaction graph
- [ ] investigation page
- [ ] approval queue
- [ ] reports
- [ ] agent trace

## Source notes

[^sources]: The supplied document contained internal chat citation IDs without source URLs. The associated claims are retained pending verification and replacement with usable links; they were not externally verified during this formatting pass.
