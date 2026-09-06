# Phase 7 — Runtime-agent foundation

The runtime-agent core is intentionally evidence-driven and read-only. `ReadOnlyRecordTools`
provides bounded canonical-record and document lookups only; it has no mutation or arbitrary-query
method. Its in-memory read model is a persistence seam for a later repository adapter.

`InvestigationBudget` enforces configured maximum LLM turns, tool calls, context bytes, and blocks
identical repeated calls. `calculate_variance`, `validate_conservation`, and `validate_journal` use
`Decimal` and remain outside model calls.

`AgentRunRequest` and `AgentRunResult` are contracts for investigation, extraction, summary, and
review-explanation capabilities. The controller that invokes these contracts only for unresolved
cases, tool access to persisted data, and audit persistence remain integration work.
