# Persisted reconciliation workspace

The first workflow vertical slice persists completed deterministic runs in the
application database.

- `POST /reconciliation/runs` accepts source and target records, runs the
  deterministic engine, persists results/exceptions, and emits a
  `RECONCILIATION_RUN_COMPLETED` audit event.
- `GET /reconciliation/runs` lists persisted runs.
- `GET /reconciliation/runs/{id}` returns results and exceptions.
- `GET /reconciliation/runs/{id}/exceptions` powers an exception queue.

`/reconciliation` in the web app displays recent run summaries. The endpoint
does not accept approvals or post accounting entries; those remain behind the
Phase 9 policy/approval boundary.
