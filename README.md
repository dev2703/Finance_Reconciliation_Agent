# Finance Reconciliation Agent

An automated account reconciliation agent built around canonical financial
contracts, deterministic rules, graph matching, ML ranking, and bounded LLM
fallback.

## Local ingestion

The MVP stores metadata in SQLite and uploaded files in `.data/objects`:

```bash
uvicorn apps.api.main:app --reload
```

Run the ingestion worker in a separate process when processing queued uploads:

```bash
python -m services.ingestion.worker
```
