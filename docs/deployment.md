# Deployment boundary

The browser calls FastAPI; FastAPI alone calls TensorMux. Therefore TensorMux
credentials must only be configured on the Python service, never in Vercel or
in a `NEXT_PUBLIC_*` variable.

## No-cost synthetic-demo deployment

The `/demo/seed-and-run` flow needs PostgreSQL but does not upload or retain
source files. It can therefore run without S3 storage and without a continuously
running ingestion worker. This is the appropriate deployment until durable object
storage and worker hosting are available.

Deploy `apps/web` to Vercel with:

```text
NEXT_PUBLIC_API_URL=https://your-python-api.example.com
```

Deploy the repository root as a Docker-based Python web service. The root
`Dockerfile` applies the idempotent migrations and listens on the platform's
`PORT` automatically. Configure the Python service with:

```text
DATABASE_URL=postgresql://...
CORS_ORIGINS=https://your-project.vercel.app
OBJECT_STORAGE_PATH=/tmp/finance-objects
NEATLOGS_API_KEY=your-neatlogs-project-key
NEATLOGS_ENDPOINT=K9wVuaPutltz-DGc3T6xrdM_1pCRQO5J
TENSORMUX_BASE_URL=https://your-tensormux-gateway.example/v1
TENSORMUX_API_KEY=your-secret-gateway-token
TENSORMUX_MODEL=glm-4-7-flash
TENSORMUX_TIMEOUT_SECONDS=30
TENSORMUX_MAX_RETRIES=2
```

When `NEATLOGS_API_KEY` is set, the API initializes the
`finance-reconciliation-investigation` workflow with OpenAI instrumentation.
Without the key, external export stays disabled and the local persisted trace remains available.

`OBJECT_STORAGE_PATH=/tmp/finance-objects` is deliberately ephemeral and is
safe only for the seed/demo flow. Do not present uploads on this deployment as
durable. A production ingestion deployment additionally needs an S3-compatible
bucket, a persistent worker service running `python -m services.ingestion.worker`,
and the same database/object-storage configuration as the API.

The optional Phase 5 synthetic artifact remains isolated at `/demo/ml-review`
and only activates when `ML_MODEL_DIRECTORY` is explicitly configured.
