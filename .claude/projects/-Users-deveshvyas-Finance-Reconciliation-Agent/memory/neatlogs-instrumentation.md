---
name: neatlogs-instrumentation
description: Neatlogs observability wired into finance-reconciliation-agent FastAPI app; NEATLOGS_API_KEY still needs to be filled in .env
metadata:
  type: project
---

Neatlogs SDK (v1.4.21) installed via uv. `neatlogs.init()` added to `apps/api/app.py` before FastAPI imports.

WORKFLOW spans added to these routes in `apps/api/routes.py`:
- `POST /reconciliation/match` → `reconcile`
- `POST /reconciliation/runs` → `create_reconciliation_run`
- `POST /reconciliation/runs/{run_id}/investigate` → `investigate_run` (primary LLM-calling route)
- `POST /demo/seed-and-run` → `seed_and_run_demo`
- `POST /documents/upload` → `upload_document`

CHAIN span on `investigate_unresolved_case` in `services/agents/controller.py`.

Manual LLM trace (`neatlogs.trace("tensormux_llm", kind="LLM")`) in `services/agents/tensormux.py` around the `httpx.Client.post()` call — TensorMux uses raw httpx (NOT an OpenAI/Anthropic SDK client), so `neatlogs.wrap()` cannot be used.

**Why:** TensorMux is an OpenAI-compatible gateway using `httpx.Client` directly, not the OpenAI Python SDK. `neatlogs.wrap()` only supports specific vendor SDK client objects and would raise TypeError on httpx.

**How to apply:** Any future LLM client added to this project: if it uses openai.OpenAI/AsyncOpenAI, use `neatlogs.wrap(client)`. If it uses raw httpx/requests, use a manual `neatlogs.trace(..., kind="LLM")` context manager around the call.

NEATLOGS_API_KEY placeholder added to `.env` and `.env.example` — the actual key must be filled in before the server can export traces.
