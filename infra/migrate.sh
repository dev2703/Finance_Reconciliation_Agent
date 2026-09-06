#!/bin/sh
set -eu

DATABASE_URL="${DATABASE_URL:-postgresql://finance_app:finance_app_dev@127.0.0.1:5433/finance_reconciliation}"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f Database/migrations/001_initial_schema.sql \
  -f Database/migrations/002_seed_fixture.sql \
  -f Database/migrations/003_ingestion_hardening.sql \
  -f Database/migrations/004_reconciliation_persistence.sql
