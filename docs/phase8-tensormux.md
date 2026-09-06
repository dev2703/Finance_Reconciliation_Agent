# Phase 8 — TensorMux and GLM integration

Runtime application agents call GLM through one OpenAI-compatible TensorMux boundary. The adapter
is synchronous today because the application-agent workflow is not yet in the async job runner.

## Configuration

Set these variables in the API/worker runtime. Never commit the real API key.

```text
TENSORMUX_BASE_URL=https://your-gateway.example/v1
TENSORMUX_API_KEY=...
TENSORMUX_MODEL=glm-4-7b-flash
TENSORMUX_TIMEOUT_SECONDS=30
TENSORMUX_MAX_RETRIES=2
TENSORMUX_INPUT_COST_PER_MILLION=0
TENSORMUX_OUTPUT_COST_PER_MILLION=0
```

The model identifier is configurable because the deployed TensorMux route name is authoritative.
Configure the cost fields for the backend if estimated-cost telemetry is required.

## Contract

`TensorMuxClient.generate_structured()` accepts an `EvidencePrompt` and a Pydantic output model. It
sends `POST /chat/completions` with a strict JSON Schema response format, then validates returned
JSON against the same model. Invalid content fails closed.

Prompts exist separately for extraction, investigation, summary, and review explanation. Every
prompt requires supplied evidence only, prohibits invented records, and requires confidence plus
unresolved questions. Evidence is capped at 30 structured items; retrieval and tool-loop limits
remain Phase 7 work.

Every success or terminal failure emits `ModelCallTelemetry`: model, tokens, latency, retry count,
status, estimated cost, case ID, and agent-run ID. Its optional sink is the seam for Phase 13
persistence; the Phase 8 adapter itself does not mutate storage.

Retries are bounded and apply only to transport failures and transient HTTP statuses.
Authentication, request validation, and malformed output fail immediately.

## Deployment acceptance

Before promoting Phase 8 to complete, run a structured request against the deployed TensorMux
gateway and confirm the GLM route returns validated JSON and token usage. No live gateway or
credentials are part of the repository test environment.
