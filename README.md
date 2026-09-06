# Finance Reconciliation Agent

An automated account reconciliation agent built around canonical financial
contracts, deterministic rules, graph matching, ML ranking, and bounded LLM
fallback.

## Phase 0 foundation

The shared Pydantic contracts live in `packages/contracts`, the FastAPI smoke
surface is in `apps/api`, and the initial PostgreSQL migrations are in
`infra/migrations`. Money fields use `Decimal` and JSON serialization preserves
decimal values as strings.

```bash
uv run pytest
uv run ruff check packages apps tests
uv run uvicorn apps.api.main:app --reload
cd apps/web && npm install && npm run dev
```

### Phase 0 execution log

Owner: Agent A
Branch/PR: `ao/finance_reconciliation_agent-3/root`
Status: [x] COMPLETE
Files: `packages/contracts`, `infra/migrations`, `apps/api`, `apps/web`
Tests: `tests/test_contracts.py`, `tests/test_api.py`
Benchmark result: Not applicable
Known limitations: The web app is a minimal smoke surface; migrations currently use ordered SQL files rather than an Alembic environment.
Next dependency: Ingestion adapters can consume the canonical contracts.
