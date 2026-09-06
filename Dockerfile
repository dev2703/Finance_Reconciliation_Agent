FROM python:3.13-slim

WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/
COPY requirements-runtime.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && uv venv && uv pip install --requirements requirements-runtime.txt
COPY . .

ENV PATH="/app/.venv/bin:$PATH"
# Hosted platforms supply PORT. Migrations are idempotent and must finish before
# the API starts so a fresh PostgreSQL database has the required tables.
CMD ["sh", "-c", "sh infra/migrate.sh && exec uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
