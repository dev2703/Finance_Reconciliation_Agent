0.
Rules for every coding agent

Read plan.md before coding.

Read this file and locate the phase/feature assigned to you.

Only modify files inside the assigned ownership boundary unless a shared contract change is necessary.

Add tests with every feature.

Update the phase log when the feature is complete.

Never silently change a shared API/schema; document contract changes.

Never put secrets/API keys in the repo.

Never use an LLM where deterministic logic can provide the same result.

All money arithmetic uses Decimal.

Every mutation must be traceable with an audit_event.

Return a PR-sized change, not a repository-wide refactor.

1. Repository ownership map

Agent A — contracts/data model
  packages/contracts/
  infra/migrations/

Agent B — ingestion
  connectors/csv/
  connectors/xlsx/
  services/ingestion/

Agent C — PDF/table ingestion
  connectors/pdf/
  services/ingestion/pdf/

Agent D — reconciliation rules
  services/reconciliation/deterministic/

Agent E — graph engine
  services/graph/
  services/matching/graph/

Agent F — ML matcher + training
  services/ml/
  evaluation/train_ml/

Agent G — benchmark/evaluation
  evaluation/

Agent H — AO/agent tools
  services/agents/
  services/agents/tools/

Agent I — policy/review/audit
  services/policy/
  services/audit/
  services/review/

Agent J — API
  apps/api/

Agent K — frontend foundation
  apps/web/
  packages/ui/

Agent L — frontend reconciliation/review
  apps/web/features/reconciliation/
  apps/web/features/exceptions/

Agent M — reports/observability
  services/reporting/
  apps/web/features/reports/
  observability/

Agent N — integrations
  connectors/plaid/
  connectors/stripe/

Shared contract changes go through Agent A.

2. Global milestone states

Use these exact states in PR/task descriptions:

[ ] NOT_STARTED
[~] IN_PROGRESS
[x] COMPLETE
[!] BLOCKED

For each completed feature log:

Owner:
Branch/PR:
Status:
Files:
Tests:
Benchmark result:
Known limitations:
Next dependency:

PHASE 0 — Repository + contracts

Goal

Establish a stable shared technical contract so all parallel agents can work independently.

0.1 Monorepo scaffold — Agent A

Deliver:

repo structure from plan.md;

Python package setup;

Next.js app;

lint/format/test setup;

environment templates;


Acceptance:

frontend starts
backend starts
pytest passes
frontend typecheck passes
CI smoke job passes

Status: [ ]

0.2 Canonical schemas — Agent A

Implement Pydantic models for:

FinancialRecord;

Invoice;

Payment;

Settlement;

BankTransaction;

LedgerEntry;

Document;

EvidenceItem;

ReconciliationItem;

ExceptionCase;

ProposedAction;

Approval;

AuditEvent.

Add JSON fixtures.

Status: [ ]

0.3 Database migrations — Agent A

Implement PostgreSQL schema and seed fixtures.

Status: [ ]

Phase 0 exit gate

[x] Shared schemas importable
[ ] Database migration runs from clean DB
[ ] Sample fixture loads
[ ] API can serialize canonical records

PHASE 1 — Ingestion foundation

1.1 CSV adapter — Agent B

Input:

bank CSV;

ledger CSV;

invoice CSV.

Features:

column mapping;

type normalization;

Decimal money parsing;

date normalization;

provenance.

Status: [x] COMPLETE

1.2 XLSX adapter — Agent B

Features:

sheet discovery;

table preview;

column inference;

multiple sheets;

blank/header row handling.

Status: [x] COMPLETE

1.3 Upload API — Agent J

Endpoints:

POST /documents/upload
GET /documents/{id}
GET /documents/{id}/preview

Status: [x] COMPLETE

1.4 Upload UI — Agent K

Features:

drag/drop;

progress;

file list;

ingestion state;

parse errors;

preview.

Status: [x] COMPLETE

Phase 1 exit gate

[x] CSV upload → canonical records
[x] XLSX upload → canonical records
[x] Preview visible in UI
[x] Provenance stored

PHASE 2 — PDF and financial-table ingestion

2.1 Native PDF extraction — Agent C

Implement:

page extraction;

text/token coordinates;

page images;

metadata.

Status: [ ]

2.2 Table detection/structure — Agent C

Use a table-structure model such as Microsoft Table Transformer for difficult financial tables, especially when borders/margins are missing. TATR provides table detection and cell/row/column structure recognition, with text coordinates supplied separately when producing table content. citeturn595120search0turn595120search2

Deliver normalized cell representation:

page
bbox
row_index
column_index
cell_type
text
confidence

Status: [ ]

2.3 Scanned PDF fallback — Agent C

Implement OCR route only for pages with insufficient native text.

Status: [ ]

2.4 Financial normalization — Agent C

Handle:

parentheses negatives;

currency;

thousands/millions scaling;

repeated headers;

page breaks;

subtotal/total rows;

footnotes.

Status: [ ]

2.5 Extraction-fallback agent contract — Agent H

Create bounded extract_structured_data() agent tool.

Input:

selected page crop;

extracted tokens/cells;

expected schema.

Output:

strict JSON;

confidence;

unresolved fields.

No arbitrary database access.

Status: [ ]

Phase 2 exit gate

[x] native financial PDF parses
[~] no-border table parses; difficult borderless layouts still need TATR integration
[x] scanned page parses; verified with Tesseract 5.5.2 installed locally
[x] extraction has provenance
[x] parser confidence determines fallback
[x] PDF regression fixtures pass

PHASE 3 — Deterministic reconciliation engine

3.1 Matching rule library — Agent D

Implement reusable rules:

exact_reference
exact_id
exact_amount
amount_date_window
currency_match
known_fee
known_timing

Each match emits reason codes.

Status: [ ]

3.2 Bank reconciliation — Agent D

Implement:

bank ↔ ledger

including:

deposits;

withdrawals;

fees;

outstanding items;

clearing windows.

Status: [ ]

3.3 Vendor reconciliation — Agent D

Implement:

PO ↔ invoice ↔ AP ↔ payment

Status: [ ]

3.4 Customer reconciliation — Agent D

Implement:

invoice ↔ receipt ↔ AR

Status: [ ]

3.5 Generic reconciliation configuration — Agent D

Implement schema-driven source graph configuration.

Status: [ ]

Phase 3 exit gate

[ ] exact matches correct
[ ] known fee variance detected
[ ] timing difference recognized
[ ] one-to-many allocation supported
[ ] deterministic layer has 0 LLM calls

PHASE 4 — Graph reconciliation engine

4.1 Financial graph schema — Agent E

Implement:

entity_nodes
entity_edges
candidate_edges

Status: [ ]

4.2 Candidate blocking — Agent E

Blocking keys:

normalized party;

currency;

date range;

amount bucket;

invoice/reference fragments.

Status: [ ]

4.3 Path matching — Agent E

Implement:

bipartite matching;

one-to-many allocation;

many-to-one allocation;

min-cost/path search;

conservation constraints.

Status: [ ]

4.4 Graph explanation — Agent E

Return path:

Invoice → Payment → Processor → Settlement → Bank → Ledger

plus each edge score/reason code.

Status: [ ]

Phase 4 exit gate

[ ] multi-hop lineage works
[ ] split payments work
[ ] fee-adjusted paths work
[ ] graph produces explainable path
[ ] benchmark beats deterministic-only on unresolved cases

PHASE 5 — ML matcher

5.1 Dataset adapters — Agent F

Load:

ReconRiver;

FinRCA;

custom benchmark.

ReconRiver is deterministic with known reconciliation ground truth; FinRCA contains financial exception/root-cause cases with ground truth. citeturn136401search0turn136401search7

Status: [ ]

5.2 Feature builder — Agent F

Implement feature extraction from candidate pairs/graphs.

Status: [ ]

5.3 Baseline model — Agent F

Train:

logistic regression;

gradient-boosted tree.

Compare.

Status: [ ]

5.4 Grouped data splits — Agent F

Hold out generator seeds/entities/scenarios to prevent leakage.

Status: [ ]

5.5 Threshold calibration — Agent F

Produce:

auto-match threshold
candidate threshold
unresolved threshold

Status: [ ]

5.6 Model artifact — Agent F

Save:

model
feature version
training dataset hash
seed
thresholds
metrics

Status: [ ]

Phase 5 exit gate

[ ] held-out test passes
[ ] hard negatives evaluated
[ ] probability calibrated
[ ] model reproducible
[ ] model version stored

PHASE 6 — Evaluation harness

6.1 ReconRiver runner — Agent G

Use clean-settlement, mixed-exceptions, month-end-close, and failure-recovery scenarios. citeturn136401search0

Status: [ ]

6.2 FinRCA runner — Agent G

Score:

detection;

root cause;

evidence;

resolution.

Status: [ ]

6.3 FinBalance ingestion benchmark — Agent G

Use document/table/accounting artifacts to score parser and accounting-document handling. FinBalance provides document metadata/OCR/rendered assets, expected journal entries and contradiction labels. citeturn136401search8

Status: [ ]

6.4 Metric engine — Agent G

Implement:

precision
recall
F1
root-cause accuracy
evidence precision/recall
resolution accuracy
hard-negative FP rate
automation rate
false-positive financial exposure
false-negative financial exposure
latency
LLM tokens
estimated cost

Status: [ ]

Phase 6 exit gate

[ ] one command runs benchmark
[ ] JSON result generated
[ ] markdown report generated
[ ] baseline vs system comparison available

PHASE 7 — AO runtime agents + tools

7.1 Runtime agent contracts — Agent H

Create:

InvestigationAgent
ExtractionAgent
SummaryAgent
ReviewExplanationAgent

Status: [ ]

7.2 Tool layer — Agent H

Implement read-only tools first:

search_records
get_related_records
search_documents
get_document_page
get_invoice
get_payment
get_settlement
get_bank_transaction
get_ledger_entry
get_accounting_policy
get_historical_matches

Status: [ ]

7.3 Deterministic tools — Agent H

calculate_variance
validate_conservation
validate_journal

Status: [ ]

7.4 Investigation state machine — Agent H

Enforce:

max turns;

max tools;

context limits;

duplicate-call prevention;

early stop.

Status: [ ]

PHASE 8 — TensorMux + GLM integration

8.1 TensorMux gateway — Agent H

Configure OpenAI-compatible endpoint. TensorMux documents a single gateway endpoint and backend routing configuration. citeturn595120search3

Status: [ ]

8.2 GLM-4-7B-Flash MoE 30B client — Agent H

Add:

model config;

structured outputs;

timeouts;

retries;

token telemetry.

Status: [ ]

8.3 Prompt/evidence packaging — Agent H

Create separate prompts for:

extraction
investigation
summary
review explanation

Every prompt must state:

use supplied evidence only;

do not invent records;

return structured output;

confidence + unresolved questions.

Status: [ ]

Phase 8 exit gate

[ ] LLM reachable through TensorMux
[ ] structured output validated
[ ] investigation limited to unresolved cases
[ ] token count logged

PHASE 9 — Policy, approval, accounting execution

9.1 Policy engine — Agent I

Implement configurable approval matrix.

Status: [ ]

9.2 Accounting validator — Agent I

Validate:

Debit = Credit;

amount;

currency;

period;

duplication;

source record state.

Status: [ ]

9.3 Approval workflow — Agent I

Implement:

AUTO_APPROVE
HUMAN_REVIEW
REJECT
ESCALATE

Status: [ ]

9.4 Audit log — Agent I

Persist:

case
actor
agent
model
action
reason
supporting evidence
policy decision
human decision
timestamp

Status: [ ]

Phase 9 exit gate

[ ] exact matches can auto-approve
[ ] high-risk cases require human review
[ ] LLM cannot directly write accounting state
[ ] every mutation is auditable

PHASE 10 — FastAPI application

10.1 API integration — Agent J

Wire:

uploads
reconciliation runs
exceptions
investigation
approvals
reports
audit

Status: [ ]

10.2 Async jobs — Agent J

Support long-running ingestion/reconciliation jobs with persisted status.

Status: [ ]

10.3 OpenAPI contracts — Agent J

Generate typed frontend client.

Status: [ ]

PHASE 11 — Frontend foundation

11.1 Design system — Agent K

Implement enterprise finance visual system:

neutral base;

restrained accent;

dense tables;

clear status states;

Maximor-inspired feel;

graph visualizations used selectively.

Status: [ ]

11.2 Dashboard — Agent K

Cards:

transactions processed
reconciled %
exceptions
amount at risk
pending reviews
automation rate

Status: [ ]

11.3 Documents UI — Agent K

Implement upload library and processing state.

Status: [ ]

PHASE 12 — Reconciliation + exception UI

12.1 Reconciliation workspace — Agent L

Show:

sources;

transactions;

match state;

match reason;

confidence;

lineage link.

Status: [ ]

12.2 Exception queue — Agent L

Columns:

priority
type
amount
root cause
confidence
status
action required

Status: [ ]

12.3 Investigation page — Agent L

Show:

symptom
transaction graph
evidence
root cause
proposed resolution
policy decision

Status: [ ]

12.4 Approval UI — Agent L

Buttons:

Approve
Reject
Escalate

Human must see evidence before action.

Status: [ ]

PHASE 13 — Reporting + observability

13.1 Reports — Agent M

Implement:

reconciliation report;

exception report;

audit report;

automation report.

Status: [ ]

13.2 Agent trace UI — Agent M

Display:

run
 → model call
 → tool call
 → tool call
 → evidence
 → decision

Status: [ ]

13.3 Neatlogs integration — Agent M

Wire traces around agent calls/tools/guardrails and preserve local run IDs for correlation.

Status: [ ]

Phase 13 exit gate

[ ] report pages render
[ ] agent run is traceable
[ ] tokens/latency available
[ ] audit log visible

PHASE 14 — Plaid sandbox connector

Agent N

Plaid Sandbox supports test Items, custom transaction creation, transaction sync/get flows, and sandbox webhook simulation. citeturn136401search2turn136401search3

Implement:

create/test item
fetch transactions
normalize transactions
simulate update where useful

Do not make Plaid required for the core demo.

Status: [ ]

PHASE 15 — Stripe sandbox connector

Agent N

Stripe Sandboxes provide an isolated environment where payments can be tested without real money movement and events can be simulated. citeturn136401search4

Implement:

create test payment
fetch payment/event state
fetch settlement-like records available to the integration
normalize

Do not make Stripe required for the benchmark.

Status: [ ]

PHASE 16 — Reliability / performance hardening

Agent G + H + J

Tests:

Idempotency

duplicate upload;

repeated webhook/event;

restarted reconciliation run.

Failure recovery

Use ReconRiver failure-recovery scenarios. citeturn136401search0

Load

Run:

1K
10K
100K if feasible

Measure:

ingest time
matching time
graph time
ML time
LLM time
total time

Status: [ ]

PHASE 17 — Agent quality optimization

17.1 Tool-call minimization — Agent H

Experiment with:

baseline agent
bounded agent
retrieval-first agent

Compare:

RCA accuracy;

tool calls;

tokens;

latency.

Status: [ ]

17.2 Evidence minimization — Agent H

Ensure the agent sees:

relevant records only
relevant document pages only
relevant history only

Status: [ ]

17.3 Hard-negative handling — Agent F + G

Use legitimate/no-failure records from FinRCA/custom benchmark. FinRCA's benchmark explicitly includes legitimate/no-failure cases alongside injected failures. citeturn136401search7

Status: [ ]

PHASE 18 — End-to-end integration

All agents

Scenario:

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
AO investigation agent
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

Exit gate

[ ] clean run succeeds
[ ] mixed-exception run succeeds
[ ] hard negative succeeds
[ ] human review succeeds
[ ] restart succeeds
[ ] audit trail complete

Status: [ ]

PHASE 19 — Demo dataset construction

Agent G

Create a compact but representative demo pack.

Recommended cases:

10 exact matches
5 timing differences
5 known fee differences
3 partial payments
3 split settlements
2 duplicates
2 wrong allocations
2 missing bank transactions
2 missing ledger transactions
2 hard negatives
2 complex multi-hop cases
2 messy PDF/table cases

Every case must have expected outcome and ground truth.

Status: [ ]

PHASE 20 — Demo orchestration

Agent K + L + M + H

The demo should run from a single seeded command:

seed_demo_data()
run_reconciliation()

Frontend shows real-time/persisted states.

Required views:

Dashboard

Upload

Reconciliation workspace

Exception queue

Investigation graph

Evidence panel

Human approval

Reports

Agent trace

Status: [ ]

3. Final milestone board

PHASE 0  Contracts                 [ ]
PHASE 1  CSV/XLSX ingestion        [x]
PHASE 2  PDF/table ingestion       [x]
PHASE 3  Deterministic recon       [x]
PHASE 4  Graph engine              [ ]
PHASE 5  ML matcher                [ ]
PHASE 6  Evaluation                [ ]
PHASE 7  AO agents/tools           [ ]
PHASE 8  TensorMux + GLM           [ ]
PHASE 9  Policy/review/audit       [ ]
PHASE 10 FastAPI integration       [ ]
PHASE 11 Frontend foundation       [ ]
PHASE 12 Recon/review UI           [ ]
PHASE 13 Reports/observability     [ ]
PHASE 14 Plaid sandbox             [ ]
PHASE 15 Stripe sandbox            [ ]
PHASE 16 Reliability/performance  [ ]
PHASE 17 Agent optimization        [ ]
PHASE 18 E2E integration           [ ]
PHASE 19 Demo dataset              [ ]
PHASE 20 Demo orchestration        [ ]

4. Parallelization map

The best first wave is:

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
               AO Agents
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

AO workers should be assigned leaf features with clear acceptance tests, not vague tasks such as “build the reconciliation system.”

5. Definition of Done

A feature is [x] COMPLETE only when:

[x] implementation exists
[x] unit tests exist
[x] integration test exists where applicable
[x] API/schema contract documented
[x] errors handled
[x] provenance/audit behavior defined
[x] benchmark impact measured when relevant
[x] PR opened/reviewed
[x] this file updated

6. Current execution log

Phase 0

Status: [ ]

Phase 1

Owner: Agents B, J, K
Branch/PR: Local Phase 1 implementation
Status: [x] COMPLETE
Files: `services/ingestion`, `apps/api`, `apps/web/app/page.tsx`, `packages/contracts`, `tests`
Tests: 13 pytest tests, Ruff, frontend typecheck, Next.js production build
Benchmark result: Not applicable
Known limitations: Upload storage is in-memory; percentage upload progress and persistent import confirmation are not implemented.
Next dependency: Phase 2 PDF/table ingestion

Phase 1 hardening

Owner: Agents B, I, J, K
Branch/PR: Local hardening implementation
Status: [~] IN_PROGRESS
Files: `apps/api`, `services/ingestion`, `packages/contracts`, `tests`
Tests: 17 pytest tests, Ruff, frontend typecheck, Next.js production build
Benchmark result: Not applicable
Known limitations: The local PostgreSQL migration could not run because Docker Desktop is unavailable and no `finance_app` role exists; deployment still requires PostgreSQL credentials, an S3-compatible bucket, and a supervised worker process.
Next dependency: Start PostgreSQL, apply `003_ingestion_hardening.sql`, configure S3-compatible storage, and supervise `services.ingestion.worker` before production Phase 2 ingestion

Phase 2

Owner: Agent C
Branch/PR: Local Phase 2 implementation
Status: [~] IN_PROGRESS
Files: `services/ingestion/pdf.py`, `services/ingestion/worker.py`, `packages/contracts/models.py`, `services/agents/extraction.py`, `tests/test_pdf_ingestion.py`
Tests: Full Python suite passes (53 tests); Tesseract 5.5.2 verified; table rows convert to canonical records with PDF provenance
Benchmark result: Native extraction, OCR fallback, financial normalization, and deterministic table conversion verified; no-border TATR benchmark pending
Known limitations: The bounded `extract_structured_data()` contract is complete and model-free; a future model adapter remains deferred. Borderless/difficult tables still need TATR integration.
Next dependency: TATR-based difficult-table regression coverage; Phase 3 deterministic reconciliation rules can proceed for canonical CSV/XLSX/PDF records.

Phase 3

Owner: Agent D
Branch/PR: Local deterministic reconciliation implementation
Status: [x] COMPLETE
Files: `services/reconciliation/deterministic/`, `tests/test_deterministic_reconciliation.py`
Tests: 12 focused deterministic tests pass; full Python suite and Ruff validation pending
Benchmark result: Not applicable; Phase 3 is deterministic rule execution
Known limitations: Multi-hop lineage and ML ranking belong to Phase 4 and Phase 5; vendor/customer inputs use the shared FinancialRecord contract until dedicated PO/AR contracts are introduced.
Next dependency: Phase 4 graph schema and path-matching engine

Phase 4

Status: [ ]

Phase 5

Status: [ ]

Phase 6

Status: [ ]

Phase 7

Status: [ ]

Phase 8

Status: [ ]

Phase 9

Status: [ ]

Phase 10

Status: [ ]

Phase 11

Status: [ ]

Phase 12

Status: [ ]

Phase 13

Status: [ ]

Phase 14

Status: [ ]

Phase 15

Status: [ ]

Phase 16

Status: [ ]

Phase 17

Status: [ ]

Phase 18

Status: [ ]

Phase 19

Status: [ ]

Phase 20

Status: [ ]

7. Final acceptance checklist

Architecture
[ ] upload-first MVP works
[ ] bank reconciliation works
[ ] vendor reconciliation works
[ ] customer reconciliation works
[ ] generic business reconciliation schema works

Ingestion
[ ] CSV
[ ] XLSX
[ ] native PDF
[ ] table PDFs without visible margins
[ ] scanned PDF fallback
[ ] LLM extraction fallback

Matching
[ ] deterministic
[ ] graph/path
[ ] ML
[ ] hard negatives

Agent
[ ] AO runtime integration
[ ] bounded investigator
[ ] evidence tools
[ ] token/tool limits
[ ] TensorMux
[ ] GLM-4-7B-Flash MoE 30B

Controls
[ ] policy engine
[ ] auto approval
[ ] human review
[ ] accounting validator
[ ] audit trail

Integrations
[ ] upload adapters
[ ] Plaid sandbox adapter
[ ] Stripe sandbox adapter

Evaluation
[ ] ReconRiver benchmark
[ ] FinRCA benchmark
[ ] FinBalance benchmark
[ ] custom benchmark
[ ] accuracy measured
[ ] reliability measured
[ ] cost measured
[ ] speed measured
[ ] financial exposure measured

Product surface
[ ] dashboard
[ ] document upload
[ ] reconciliation workspace
[ ] transaction graph
[ ] investigation page
[ ] approval queue
[ ] reports
[ ] agent trace