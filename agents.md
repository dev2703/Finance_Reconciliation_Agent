# Finance Reconciliation — Implementation Phases

Use this document for **delivery phases, owners, acceptance criteria, and progress**.
Use [plan.md](plan.md) for the target architecture and rationale.

> **Numbering:** Phase 5 is the [TensorMux candidate ranker](#phase-5--tensormux-candidate-ranker).
> Section 5 of [plan.md](plan.md#section-5-connector-architecture) is connector architecture.
> Phase numbers below are preserved from the supplied roadmap.

## Current milestone board

This is the single current phase-status overview, based on the local review on **2026-09-06**.
`IN_PROGRESS` means some code exists; it does not establish that the exit gate passed.
`NOT_STARTED` means no corresponding implementation was found in that review.

| Phase | Deliverable | Current status | Evidence / remaining work |
|---|---|---|---|
| 0 | [Repository + contracts](#phase-0--repository--contracts) | `IN_PROGRESS` | Clean PostgreSQL migration and fixture loading pass locally; CI now runs PostgreSQL, migrations, backend checks, frontend typecheck/build. Remote CI acceptance remains. |
| 1 | [Ingestion foundation](#phase-1--ingestion-foundation) | `IN_PROGRESS` | CSV/XLSX upload, worker, preview, confirmation, and persistence exist; hardening issues remain. |
| 2 | [PDF and financial-table ingestion](#phase-2--pdf-and-financial-table-ingestion) | `IN_PROGRESS` | Native, text-aligned no-border tables, and confidence-driven OCR fallback are tested; model fallback integration and broader fixtures remain. |
| 3 | [Deterministic reconciliation engine](#phase-3--deterministic-reconciliation-engine) | `IN_PROGRESS` | One-to-one, one-to-many, many-to-one, audit output, stateless matching, and persisted reconciliation runs are tested. |
| 4 | [Graph reconciliation engine](#phase-4--graph-reconciliation-engine) | `IN_PROGRESS` | Directed lineage and conserved split/fee allocation are tested; comparative benchmark acceptance remains. |
| 5 | [TensorMux candidate ranker](#phase-5--tensormux-candidate-ranker) | `IN_PROGRESS` | Local-model work is superseded. TensorMux must rank complete candidate groups through a versioned, evidence-bound, review-only contract; live and representative-data acceptance remain. |
| 6 | [Evaluation harness](#phase-6--evaluation-harness) | `COMPLETE` | Offline ReconRiver/FinRCA/FinBalance runners, metric engine, CLI, JSON/Markdown reports, and baseline comparison pass on fixture packs; external dataset acceptance remains optional. |
| 7 | [Runtime application agents + tools](#phase-7--runtime-application-agents--tools) | `IN_PROGRESS` | Bounded evidence-only investigation controller routes persisted unresolved runs through TensorMux; broader persisted record tools remain. |
| 8 | [TensorMux + GLM integration](#phase-8--tensormux--glm-integration) | `IN_PROGRESS` | OpenAI-compatible client, strict outputs, evidence prompts, retries, and telemetry are implemented; live TensorMux/GLM reachability remains deployment acceptance. |
| 9 | [Policy, approval, accounting execution](#phase-9--policy-approval-accounting-execution) | `IN_PROGRESS` | Review decisions persist through audited API controls; deterministic journal validation exists. External accounting execution remains absent. |
| 10 | [FastAPI application](#phase-10--fastapi-application) | `IN_PROGRESS` | Persisted reconciliation, exceptions, TensorMux investigations, approvals, reports, audit, traces, ingestion, and demo routes exist; durable async reconciliation jobs remain. |
| 11 | [Frontend foundation](#phase-11--frontend-foundation) | `IN_PROGRESS` | Upload and dashboard views with the finance visual foundation exist; broader UI foundation remains. |
| 12 | [Reconciliation + exception UI](#phase-12--reconciliation--exception-ui) | `IN_PROGRESS` | Run workspace, exception queue, investigation/evidence view, and approval UI exist; deeper graph visualization remains. |
| 13 | [Reporting + observability](#phase-13--reporting--observability) | `IN_PROGRESS` | Persisted GLM telemetry, global audit/trace APIs, operational reports, report/trace UI, and credential-gated Neatlogs instrumentation exist; live export acceptance remains. |
| 14 | [Plaid sandbox connector](#phase-14--plaid-sandbox-connector) | `IN_PROGRESS` | Sandbox client, custom transaction simulation, webhook trigger, and bank-record normalization are implemented and mock-tested; live Sandbox acceptance remains. |
| 15 | [Stripe sandbox connector](#phase-15--stripe-sandbox-connector) | `IN_PROGRESS` | Sandbox PaymentIntent/event/balance-transaction client and payment/settlement normalization are implemented and mock-tested; live Sandbox acceptance remains. |
| 16 | [Reliability / performance hardening](#phase-16--reliability--performance-hardening) | `IN_PROGRESS` | Ingestion retries and upload deduplication exist; restart recovery and performance acceptance remain incomplete. |
| 17 | [Agent quality optimization](#phase-17--agent-quality-optimization) | `NOT_STARTED` | No corresponding implementation found in the reviewed checkout. |
| 18 | [End-to-end integration](#phase-18--end-to-end-integration) | `IN_PROGRESS` | Demo seed → deterministic reconcile → persisted run/exceptions/review/reports works on Docker Postgres; full agent/policy/accounting E2E remains. |
| 19 | [Demo dataset construction](#phase-19--demo-dataset-construction) | `IN_PROGRESS` | A deterministic 40-case pack covers all recommended categories with expected outcomes; end-to-end system predictions remain integration work. |
| 20 | [Demo orchestration](#phase-20--demo-orchestration) | `IN_PROGRESS` | `POST /demo/seed-and-run` and UI seed action persist a run; frontend workspace/exception/review/report views exist. |

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
| F | TensorMux ranking + evaluation | `services/matching/tensormux/`, `evaluation/tensormux/` |
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

- [x] native financial PDF parses
- [x] no-border table parses
- [x] scanned page parses through confidence-driven OCR
- [x] extraction has provenance
- [x] parser confidence determines fallback
- [x] local PDF regression fixtures pass

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

- [x] exact matches correct
- [x] known fee variance detected
- [x] timing difference recognized
- [x] one-to-many and many-to-one allocation supported
- [x] deterministic layer has 0 LLM calls

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

- [x] multi-hop lineage works
- [x] split payments work
- [x] fee-adjusted paths work
- [x] graph produces explainable path
- [ ] benchmark beats deterministic-only on unresolved cases

## Phase 5 — TensorMux candidate ranker

**Current status: IN_PROGRESS (2026-09-06).**

The target design uses no local trained matcher or serialized model artifact. Existing local-model
code and synthetic results are historical implementation evidence only and must not be wired into
the production path. Candidate ranking is performed through TensorMux, with deterministic blocking,
financial arithmetic, validation, policy, and accounting mutation remaining outside the model.

### 5.1 Dataset adapters — Agent F

**Load:**

- ReconRiver
- FinRCA
- custom benchmark.

ReconRiver is deterministic with known reconciliation ground truth; FinRCA contains financial exception/root-cause cases with ground truth. [^sources]

**Status: IN_PROGRESS.** Strict custom JSONL, ReconRiver clean ORDER links, and FinRCA raw-clean full allocations are supported. Broader external cases remain.

### 5.2 Evidence builder — Agent F

Build compact, deterministic evidence bundles from complete graph-blocked candidate groups.
Include computed amount/date/reference/party facts, graph paths, competing candidates, provenance,
and evidence IDs. All money arithmetic remains Decimal-based and outside TensorMux.

**Status: IN_PROGRESS.** Existing deterministic features may be reused as evidence, but the
versioned TensorMux evidence contract and full competing-group packaging are not complete.

### 5.3 TensorMux ranking contract — Agent F + H

One competing group is the full connected component of graph-blocked candidate edges that share a
source or target record. Assert completeness before the call. A group may contain at most 100
candidates, 30 evidence items, and 24,000 input tokens. Never truncate: an oversized group returns
`UNRESOLVED/GROUP_TOO_LARGE`. Require one strict group response containing:

- `group_id` and an ordered `ranked_candidates` list
- for each supplied candidate: candidate ID, `HUMAN_REVIEW` or `UNRESOLVED`, confidence, reason
  codes, supporting/contradicting evidence IDs, and unresolved questions
- an explicit `NO_MATCH` option for the group
- decision-manifest hash, prompt hash, schema hash, TensorMux route, and observed backend version.

The ranker must never enable automatic accounting action.

**Status: NOT_STARTED.** The generic TensorMux client exists, but it is not connected to candidate ranking.

### 5.4 Sealed evaluation splits — Agent F + G

Hold out generator seeds, entities, scenarios, months, and failure classes so prompt, routing, or
threshold decisions cannot leak test evidence. Any prompt, schema, route, model, evidence-builder,
or policy change invalidates the sealed result and requires reevaluation.

**Status: IN_PROGRESS.** Existing grouped-split utilities can be reused, but they must be applied to
the TensorMux decision bundle rather than local training.

### 5.5 Empirical decision calibration — Agent F + G

**Produce:**

- human-review threshold
- unresolved boundary

Treat model confidence as an untrusted score. Evaluate thresholds on a separate calibration set for
each immutable TensorMux decision bundle. Phase 5 emits only `HUMAN_REVIEW` or `UNRESOLVED`;
`AUTO_APPROVE` remains exclusively deterministic and policy-controlled.

**Status: NOT_STARTED.** Local-model calibration does not satisfy this TensorMux acceptance gate.

### 5.6 TensorMux decision bundle — Agent F + H

**Save:**

- TensorMux route and pinned backend model version
- prompt and strict-output schema hashes
- evidence-builder version
- calibration and evaluation dataset hashes
- dataset-generation seed
- inference parameters (`temperature`, `top_p`, `max_tokens`, response format)
- thresholds
- metrics
- validated relationships and policy version

Do not save or load `model.joblib` or any other local executable model artifact.
The backend version must come from a configured TensorMux response field/header, must be present,
and must equal the manifest pin; mismatch returns `UNRESOLVED/BACKEND_VERSION_MISMATCH`. Cache
validated results by `(decision_manifest_hash, evidence_bundle_hash)`. On an unpublished sealed
set, run each uncached group three times; candidate classification disagreement must be <= 1%, and
any individual disagreement remains unresolved.

**Status: NOT_STARTED.** Existing local artifacts are superseded by this manifest.

### 5.7 Review-only runtime integration — Agent F + H + I + J

Replace the local-artifact API path with a bounded TensorMux call. Validate every response against
the supplied candidate/evidence universe, fail closed on timeout or invalid output, emit model-call
telemetry and audit events, and never mutate accounting state.

Use distinct failure reasons and audit events: `TENSORMUX_TIMEOUT`, `TENSORMUX_RATE_LIMITED`,
`INVALID_RANKING_SCHEMA`, `UNKNOWN_EVIDENCE_ID`, `BACKEND_VERSION_MISMATCH`, `GROUP_TOO_LARGE`, and
`RANKING_BUDGET_EXHAUSTED`. Persist the complete validated ranker decision, evidence-bundle hash,
decision-manifest hash/version, observed backend version, and model-call IDs in PostgreSQL.
Enforce per-group and per-run limits for calls, input/output tokens, elapsed time, and estimated
cost. Exhaustion is terminal for that group and returns `UNRESOLVED/RANKING_BUDGET_EXHAUSTED`.

Modal is not a Phase 5 dependency or acceptance target. Production import-graph tests apply to the
FastAPI API and whichever durable worker entrypoint is selected. Vercel may host the frontend and
short control requests, but a deployment-platform choice must not alter the TensorMux contract.

Agent F owns candidate/evidence semantics and evaluation; Agent H owns the shared TensorMux client,
prompt execution, and telemetry. Neither may duplicate the other's gateway or ranking policy.

**Status: NOT_STARTED.** The current local `ML_MODEL_DIRECTORY` runtime path is not the target design.

### 5.8 Local-model decommission — Agent F + H + J

The first implementation PR must remove the local runtime before adding TensorMux ranking:

1. Delete `/demo/ml-review` and any alias, `ML_MODEL_DIRECTORY`, `docs/phase5-runtime.md`, and
   `docs/phase5-synthetic-demo.md`; remove the optional-artifact statement from
   `docs/deployment.md`, and update API tests to prove every local-artifact route is absent.
2. Move provider-neutral dataset contracts/adapters into `evaluation/datasets/` and break their
   import of `services.ml.training`; retain no training-example converter in the runtime graph.
3. Move any historically useful local-model experiments under `evaluation/legacy_ml/`, or delete
   them. Production packages must not import `services/ml/{training,calibration,artifact,model,
   workflow,selection,features,contracts}` or its package `__init__`.
4. Remove `scikit-learn`, `xgboost`, `joblib`, and `sentence-transformers` from
   `requirements-runtime.txt` and `pyproject.toml` `[project].dependencies`. Retain
   `torch`/`transformers` only in the PDF/TATR worker dependency set. Extend
   `tests/test_runtime_dependencies.py` to assert the four prohibited packages are absent, and use
   deterministic string similarity instead of local description embeddings.

Required tests must prove that the production runtime uses a versioned TensorMux decision manifest,
starts without local model files or the four prohibited dependencies, contains no reachable `joblib.load` or
`model.joblib` path, and fails closed to `UNRESOLVED` when TensorMux is unavailable.

**Status: NOT_STARTED.** The historical modules remain present and the API still imports the local
ranker; they are prohibited from future production integration until this migration is completed.

### Phase 5 exit gate

- [ ] complete competing candidate groups are ranked through TensorMux
- [ ] strict structured output and supplied-evidence references are validated
- [ ] authoritative unpublished custom sealed set has at least 500 groups and 100 hard-negative groups
- [ ] `HUMAN_REVIEW` precision >= 98% and hard-negative review false-positive rate <= 1%
- [ ] TensorMux reduces unresolved groups by >= 10% relative to deterministic+graph on the same set without violating the precision floor
- [ ] thresholds are selected on calibration data and frozen before the sealed run
- [ ] prompt, schema, route, backend model, datasets, thresholds, and metrics are versioned
- [ ] TensorMux failure degrades to `UNRESOLVED`
- [ ] no local trained model or executable model artifact is required
- [ ] historical local-model modules are unreachable from API and worker runtime graphs
- [ ] tests prove no production `model.joblib`, `joblib.load`, or `ML_MODEL_DIRECTORY` path
- [ ] three-run uncached decision disagreement <= 1%; disagreements remain unresolved
- [ ] runtime manifest hash equals the last evaluated manifest hash in CI
- [ ] per-group and per-run token, latency, call-count, and cost budgets fail closed when exhausted
- [ ] every output is review-only and every mutation remains outside the model boundary
- [ ] process gate: independent review approves the complete Phase 5 evidence

For the precision gate, a `HUMAN_REVIEW` candidate is correct only when it is a ground-truth link;
precision is correct review candidates divided by all candidates classified `HUMAN_REVIEW`.

## Phase 6 — Evaluation harness

### 6.1 ReconRiver runner — Agent G

Use clean-settlement, mixed-exceptions, month-end-close, and failure-recovery scenarios. [^sources]

**Status: [x] COMPLETE.** The runner discovers the four named scenario directories, validates
inputs, and scores prediction output against fixture packs.

### 6.2 FinRCA runner — Agent G

**Score:**

- detection
- root cause
- evidence
- resolution.

**Status: [x] COMPLETE.** Detection, root cause, evidence, resolution, hard-negative exposure,
latency, token, and cost scoring are supported.

### 6.3 FinBalance ingestion benchmark — Agent G

Use document/table/accounting artifacts to score parser and accounting-document handling. FinBalance provides document metadata/OCR/rendered assets, expected journal entries and contradiction labels. [^sources]

**Status: [x] COMPLETE.** Document text, expected journals, contradiction labels, fields,
Decimal amounts, and provenance are validated; the runner scores parser/accounting outputs.

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

**Status: [x] COMPLETE.** Precision, recall, F1, RCA/evidence/resolution, hard-negative,
automation, exposure, latency, token, and estimated-cost metrics are available.

### Phase 6 exit gate

- [x] one command runs benchmark (`python -m evaluation --suite all`)
- [x] JSON result generated
- [x] markdown report generated
- [x] baseline vs system comparison available

The completed Phase 6 fixture harness is infrastructure only. The new deterministic+graph versus
TensorMux ranking comparison remains a Phase 5 acceptance dependency, and all Phase 6 tests must
remain green after the Phase 5.8 relocation.

## Phase 7 — Runtime application agents + tools

### 7.1 Runtime agent contracts — Agent H

**Create:**

- InvestigationAgent
- ExtractionAgent
- SummaryAgent
- ReviewExplanationAgent
- CandidateRankingAgent

**Status: IN_PROGRESS.** Bounded request/result contracts are available for the original four agent
kinds; the candidate-ranking contract and controller routing are not yet integrated.

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

**Status: Partially implemented and tested locally.** A capped, read-only canonical-record/document
read model provides search, related-record, document-page, and typed record retrieval; policy and
historical-match tools plus persistence-backed retrieval remain pending.

### 7.3 Deterministic tools — Agent H

- calculate_variance
- validate_conservation
- validate_journal

**Status: Implemented and tested.** Exact-Decimal variance, conservation, and journal checks exist.

### 7.4 Investigation state machine — Agent H

**Enforce:**

- max turns
- max tools
- context limits
- duplicate-call prevention
- early stop.

**Status: Implemented and tested locally.** Turn, tool-call, context-byte, and duplicate-call
limits are enforced by `InvestigationBudget`; workflow orchestration remains pending.

## Phase 8 — TensorMux + GLM integration

### 8.1 TensorMux gateway — Agent H

Configure OpenAI-compatible endpoint. TensorMux documents a single gateway endpoint and backend routing configuration. [^sources]

**Status: Implemented and tested locally.** The configurable client uses the OpenAI-compatible
`/chat/completions` boundary. Live gateway reachability requires deployment credentials.

### 8.2 GLM-4.7-Flash MoE 30B client — Agent H

**Add:**

- model config
- structured outputs
- timeouts
- retries
- token telemetry.

**Status: Implemented and tested locally.** Model route, strict Pydantic/JSON Schema outputs,
timeouts, bounded transient retries, token telemetry, and cost estimation are supported.

### 8.3 Prompt/evidence packaging — Agent H

**Create separate prompts for:**

- extraction
- investigation
- summary
- review explanation
- candidate ranking

**Every prompt must state:**

- use supplied evidence only
- do not invent records
- return structured output
- confidence + unresolved questions.

**Status: IN_PROGRESS.** Separate evidence-only packages exist for extraction, investigation,
summary, and review explanation; candidate ranking remains to be added.

### Phase 8 exit gate

- [ ] LLM reachable through TensorMux
- [x] structured output validated
- [ ] investigation limited to unresolved cases
- [x] token count logged
- [ ] complete candidate groups rank through the versioned TensorMux decision manifest

## Phase 9 — Policy, approval, accounting execution

### 9.1 Policy engine — Agent I

Implement configurable approval matrix.

**Status: Implemented and tested locally.** A configurable first-match policy has safe human-review defaults and supports AUTO_APPROVE, HUMAN_REVIEW, REJECT, and ESCALATE outcomes.

### 9.2 Accounting validator — Agent I

**Validate:**

- Debit = Credit
- amount
- currency
- period
- duplication
- source record state.

**Status: Implemented and tested locally.** Decimal journal balancing, currency, closed period, duplicate, source validity, reconciliation state, and LLM-journal rejection are deterministic pre-posting checks.

### 9.3 Approval workflow — Agent I

**Implement:**

- AUTO_APPROVE
- HUMAN_REVIEW
- REJECT
- ESCALATE

**Status: Implemented and tested locally.** In-memory review queue enforces a single human decision and audits queueing and decisions; persistence/API integration remains pending.

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

**Status: Implemented for Phase 9 workflow mutations.** Audit events include the actor, decision/reason, entity, timestamp, and policy decision details. Full database persistence is an API integration dependency.

### Phase 9 exit gate

- [x] exact matches can auto-approve
- [x] high-risk cases require human review
- [x] LLM-generated journals rejected before posting
- [x] Phase 9 workflow mutations are auditable

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

**Status: Partially implemented and tested locally.** Upload endpoints and an ingestion-backed
`GET /dashboard/metrics` endpoint are wired; reconciliation, investigation, approval, report, and
audit routes remain pending.

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

**Status: Implemented and tested locally.** The upload and dashboard views share a restrained,
responsive finance-oriented visual system with clear status states.

### 11.2 Dashboard — Agent K

**Cards:**

- transactions processed
- reconciled %
- exceptions
- amount at risk
- pending reviews
- automation rate

**Status: Implemented and tested locally.** `/dashboard` renders the required KPI cards with a
safe empty state until the API metrics endpoint is available.

### 11.3 Documents UI — Agent K

Implement upload library and processing state.

**Status: Existing upload UI retained.** Dashboard navigation links to the document upload view.

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

**Status: Implemented as deterministic payloads.** Reconciliation, exception, audit, and automation
reports are assembled from supplied records and computed metrics; report API/UI remain pending.

### 13.2 Agent trace UI — Agent M

**Display:**

- run
- → model call
- → tool call
- → tool call
- → evidence
- → decision

**Status: Local trace contract implemented and tested.** Stable run IDs correlate model, tool,
evidence, decision, guardrail, completion, and failure events; trace UI remains pending.

### 13.3 Neatlogs integration — Agent M

Wire traces around agent calls/tools/guardrails and preserve local run IDs for correlation.

**Status: IN_PROGRESS.** Credential-gated Neatlogs workflow, route, agent-chain, and TensorMux LLM
instrumentation are configured; local run events remain available without external export. Live
export acceptance with a deployed project key remains.

### Phase 13 exit gate

- [ ] report pages render
- [x] agent run is traceable locally
- [x] tokens/latency available in trace summaries
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

**Status: IN_PROGRESS.** A configurable Sandbox client creates test Item tokens, exchanges
tokens, fetches transaction-sync pages, creates custom Sandbox transactions, triggers webhooks,
and normalizes provider payloads to `BankTransaction`. Live Sandbox credentials are still needed.

## Phase 15 — Stripe sandbox connector

**Owner:** Agent N

Stripe Sandboxes provide an isolated environment where payments can be tested without real money movement and events can be simulated. [^sources]

**Implement:**

- create test payment
- fetch payment/event state
- fetch settlement-like records available to the integration
- normalize

Do not make Stripe required for the benchmark.

**Status: IN_PROGRESS.** A configurable Sandbox client creates test PaymentIntents and fetches
payments, events, and balance transactions. PaymentIntents normalize to `Payment`; balance
transactions normalize to `Settlement`. Live Sandbox credentials are still needed.

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
- TensorMux ranking time
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
TensorMux candidate rank
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

**Current status: Implemented and tested locally.** `seed_demo_data()` produces 40 deterministic
cases spanning every recommended category, with expected outcomes and ground truth. Current system
accuracy must be supplied by the integrated reconciliation workflow rather than acceptance fixtures.

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
      TensorMux rank   Evaluation
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

### Phase 5 TensorMux supersession decision — 2026-09-06

- **Owner:** Agents F, H, I, J, G
- **Branch/PR:** `ao/finance_reconciliation_agent-4/root`; design review in progress
- **Status:** [~] IN_PROGRESS
- **Files:** `agents.md`, `plan.md`
- **Tests:** Documentation consistency and diff checks only; runtime migration tests are specified but not implemented
- **Benchmark result:** None yet; the authoritative unpublished TensorMux sealed-set gate is defined above
- **Known limitations:** Historical local-model code and API wiring remain reachable until the mandatory first migration PR lands
- **Next dependency:** Remove the local runtime/import graph, then implement and evaluate the versioned TensorMux ranking manifest

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

### Phase 8 implementation entry — 2026-09-06

- **Owner:** Agent H
- **Branch/PR:** Local Phase 8 implementation; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `services/agents/tensormux.py`, `services/agents/prompts.py`, `.env.example`, `docs/phase8-tensormux.md`, `tests/test_tensormux.py`
- **Tests:** 112 pytest tests pass; Phase 8 agent paths and tests pass Ruff
- **Benchmark result:** Not applicable; mocked transient retry and strict-output protocol tests pass
- **Known limitations:** No deployed TensorMux/GLM endpoint or credentials were available for live reachability acceptance; Phase 7 unresolved-case routing is not implemented
- **Next dependency:** Configure the deployed TensorMux route, run the documented live structured-output check, and integrate the client with the Phase 7 workflow

### Phase 7 implementation entry — 2026-09-06

- **Owner:** Agent H
- **Branch/PR:** Local Phase 7 foundation; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `services/agents/runtime.py`, `services/agents/tools.py`, `docs/phase7-runtime-agents.md`, `tests/test_agent_runtime.py`
- **Tests:** Runtime-agent tests pass; agent paths pass Ruff
- **Benchmark result:** Not applicable
- **Known limitations:** Read tools use an injected in-memory read model; controller routing, persisted tool adapters, and audit integration remain unfinished
- **Next dependency:** Wire repositories and unresolved-case routing through the reconciliation workflow

### Phase 11 dashboard implementation entry — 2026-09-06

- **Owner:** Agent K
- **Branch/PR:** Local Phase 11 dashboard foundation; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `apps/web/app/dashboard/`, `apps/web/app/globals.css`, `apps/web/app/layout.tsx`, `apps/web/app/page.tsx`
- **Tests:** `npm run typecheck` and `npm run build` pass
- **Benchmark result:** Not applicable
- **Known limitations:** Reconciliation, exception, review, and automation metrics are zero until
  their workflow state is persisted
- **Next dependency:** Add persisted reconciliation and review metrics to the API

### Phase 9 controls implementation entry — 2026-09-06

- **Owner:** Agent I
- **Branch/PR:** Local Phase 9 controls implementation; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `services/policy/`, `services/review/`, `services/audit/`, `tests/test_policy_controls.py`
- **Tests:** 4 focused pytest tests pass
- **Benchmark result:** Not applicable
- **Known limitations:** Controls are in-memory modules; no API, database persistence, accounting posting adapter, or end-to-end reconciliation integration yet exists.
- **Next dependency:** Phase 10 routes/persistence and an accounting execution adapter must invoke policy and validation before any write.

### Phase 14–15 connector implementation entry — 2026-09-06

- **Owner:** Agent N
- **Branch/PR:** Local connector implementation; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `connectors/plaid/`, `connectors/stripe/`, `.env.example`, `tests/test_sandbox_connectors.py`
- **Tests:** Four mocked HTTP and normalization tests pass; connector paths pass Ruff
- **Benchmark result:** Not applicable; sandboxes are integration environments, not benchmark data
- **Known limitations:** No live Plaid or Stripe Sandbox credentials were supplied. Stripe's actual
  asynchronous event delivery is fetched rather than fabricated by the connector.
- **Next dependency:** Provide restricted Sandbox keys and run live create/fetch/normalize acceptance checks.

### Phase 6 + Phase 19 evaluation implementation entry — 2026-09-06

- **Owner:** Agent G
- **Branch/PR:** Local evaluation and demo-pack implementation; PR not opened
- **Status:** [x] COMPLETE
- **Files:** `evaluation/` (metrics, runners, fixtures, CLI, demo/harness), `docs/phase6-phase19-evaluation.md`, `tests/test_evaluation_harness.py`, `tests/test_demo_evaluation.py`
- **Tests:** Fixture suite runners, metric engine, CLI fixture + demo modes, and 40-case demo comparison pass
- **Benchmark result:** Offline fixture packs and demo acceptance fixtures produce JSON/Markdown baseline-vs-system reports; not live E2E accuracy
- **Known limitations:** External ReconRiver/FinRCA/FinBalance packs and real workflow prediction exports are not required for local exit-gate; replace prediction JSONL to measure the live system
- **Next dependency:** Emit prediction JSONL from the Phase 18 reconciliation workflow and optionally point `--fixtures` at external packs

### Phase 10/12/18/20 Postgres + demo path entry — 2026-09-06

- **Owner:** Agents J, L, G, K
- **Branch/PR:** Local Docker Postgres + API/UI orchestration; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `infra/docker-compose.yml`, `Database/migrations/004_reconciliation_persistence.sql`, `apps/api/`, `services/demo/`, `apps/web/app/{reconciliation,exceptions,investigation,reviews,reports}/`, `tests/test_demo_orchestration.py`
- **Tests:** Demo orchestration + API suite pass (16 focused); frontend typecheck passes; Postgres smoke via `POST /demo/seed-and-run`
- **Benchmark result:** Demo pack yields matched + exception outcomes on deterministic matching against Docker Postgres
- **Known limitations:** Local Homebrew Postgres occupies `:5432`; finance DB uses `:5433`. API default port is `8001` to avoid collision with other local services. Graph visualization and live TensorMux/Plaid/Stripe remain open.
- **Next dependency:** Supervise API on `:8001`, point the web app at it, and optionally wire live TensorMux for investigation

### Phase 13 reporting/observability foundation entry — 2026-09-06

- **Owner:** Agent M
- **Branch/PR:** Local reporting/trace foundation; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `services/reporting/`, `observability/`, `tests/test_reporting_observability.py`
- **Tests:** Deterministic report and append-only correlated trace tests pass
- **Benchmark result:** Not applicable
- **Known limitations:** No report/trace API, database persistence, frontend views, or Neatlogs exporter exists yet
- **Next dependency:** Persist trace/report projections and expose them through Phase 10 and Phase 13 UI routes

### Phase 2–4 hardening entry — 2026-09-06

- **Owner:** Agents C, D, E, J
- **Branch/PR:** Local PDF/reconciliation hardening; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `services/ingestion/pdf.py`, `services/reconciliation/`, `apps/api/routes.py`, `docs/phase2-phase4-hardening.md`, targeted tests
- **Tests:** No-border table, OCR-confidence fallback, many-to-one workflow/API, directed split, and fee-adjusted graph regressions pass
- **Benchmark result:** Phase 4 comparative benchmark remains pending
- **Known limitations:** Reconciliation API is stateless; structured extraction model fallback and broad scanned/no-border fixture packs remain integration acceptance
- **Next dependency:** Persist reconciliation runs, connect low-confidence extraction to the Phase 8 model client, and benchmark graph resolution against deterministic-only cases

### Phase 13 Neatlogs integration entry — 2026-09-07

- **Owner:** Agent M
- **Branch/PR:** Local Neatlogs integration; PR not opened
- **Status:** [~] IN_PROGRESS
- **Files:** `apps/api/`, `services/agents/`, `.env.example`, `.python-version`, `pyproject.toml`, `infra/docker-compose.yml`, `requirements-runtime.txt`, `docs/deployment.md`, `tests/test_neatlogs_config.py`, `tests/test_runtime_dependencies.py`
- **Tests:** Focused Ruff checks pass; Neatlogs, TensorMux, API, local observability, and runtime dependency regression tests pass
- **Benchmark result:** Not applicable
- **Known limitations:** Live export has not been accepted against a deployed Neatlogs project key
- **Next dependency:** Configure `NEATLOGS_API_KEY` in the Python deployment and verify exported investigation traces

### Phase 0 CI exclusion entry — 2026-09-07

- **Owner:** CI maintenance
- **Branch/PR:** `ao/finance_reconciliation_agent-16/ruff-skill-exclusion` (separate from PR 7)
- **Status:** [x] COMPLETE locally; remote CI pending
- **Files:** `pyproject.toml`, `tests/test_ruff_config.py`, `agents.md`
- **Tests:** `uv run ruff format --check .` (118 files already formatted), `uv run ruff check .` (passed), `uv run pytest` (162 passed, 7 dependency deprecation warnings)
- **Benchmark result:** Not applicable; CI configuration only
- **Known limitations:** Exclusion applies to recursive discovery; explicit file arguments retain Ruff's existing behavior. Bundled third-party skills and Phase 5 content are unchanged.
- **Next dependency:** Remote CI acceptance

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
- [ ] TensorMux candidate ranking
- [ ] hard negatives

### Agent

- [ ] Runtime application-agent integration
- [ ] bounded investigator
- [ ] evidence tools
- [ ] token/tool limits
- [ ] TensorMux
- [ ] GLM-4.7-Flash MoE 30B

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
