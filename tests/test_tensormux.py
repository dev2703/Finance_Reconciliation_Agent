from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from packages.contracts.models import ContractModel
from services.agents.prompts import AgentTask, EvidencePrompt, build_messages
from services.agents.tensormux import TensorMuxClient, TensorMuxError, TensorMuxSettings


class InvestigationOutput(ContractModel):
    root_cause: str | None
    confidence: Decimal
    unresolved_questions: list[str]


def _settings(**overrides: object) -> TensorMuxSettings:
    return TensorMuxSettings(
        api_key="test-secret",
        base_url="https://gateway.test/v1",
        model="glm-test",
        **overrides,
    )


def test_every_prompt_enforces_evidence_only_structured_output():
    for task in AgentTask:
        messages = build_messages(
            EvidencePrompt(
                task=task,
                evidence=[{"record_id": "r1", "amount": "10.00"}],
                expected_schema={"confidence": "decimal", "unresolved_questions": "array"},
            )
        )
        system = messages[0]["content"].lower()
        assert "supplied evidence only" in system
        assert "do not invent records" in system
        assert "return only json" in system
        assert "confidence and unresolved_questions" in system


def test_structured_call_validates_output_and_records_telemetry():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(__import__("json").loads(request.content))
        assert request.headers["authorization"] == "Bearer test-secret"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"root_cause":"fee","confidence":"0.82","unresolved_questions":[]}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    telemetry = []
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = TensorMuxClient(
        _settings(input_cost_per_million=Decimal(2), output_cost_per_million=Decimal(4)),
        http_client=http_client,
        telemetry_sink=telemetry.append,
    )
    result = client.generate_structured(
        EvidencePrompt(
            task=AgentTask.INVESTIGATION,
            evidence=[{"variance": "2.00"}],
            expected_schema=InvestigationOutput.model_json_schema(),
        ),
        InvestigationOutput,
        case_id="case-1",
        agent_run_id="run-1",
    )

    assert result.output.confidence == Decimal("0.82")
    assert result.telemetry.prompt_tokens == 100
    assert result.telemetry.retry_count == 0
    assert result.telemetry.estimated_cost == Decimal("0.00028")
    assert result.telemetry.case_id == "case-1"
    assert telemetry == [result.telemetry]
    assert captured[0]["response_format"]["json_schema"]["strict"] is True


def test_gateway_schema_removes_decimal_regex_but_keeps_response_validation():
    captured: list[dict] = []
    content = '{"root_cause":null,"confidence":"0.5","unresolved_questions":[]}'

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": content}}]},
        )

    client = TensorMuxClient(
        _settings(), http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = client.generate_structured(
        EvidencePrompt(task=AgentTask.INVESTIGATION, expected_schema={}, evidence=[]),
        InvestigationOutput,
    )
    schema = __import__("json").dumps(captured[0]["response_format"]["json_schema"]["schema"])
    assert '"pattern"' not in schema
    assert result.output.confidence == Decimal("0.5")


def test_retryable_failure_retries_and_reports_count():
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": "busy"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": {
                                "root_cause": None,
                                "confidence": "0",
                                "unresolved_questions": ["missing evidence"],
                            }
                        }
                    }
                ],
                "usage": {},
            },
        )

    client = TensorMuxClient(
        _settings(max_retries=1),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    result = client.generate_structured(
        EvidencePrompt(task=AgentTask.INVESTIGATION, expected_schema={}, evidence=[]),
        InvestigationOutput,
    )
    assert calls == 2
    assert result.telemetry.retry_count == 1


def test_invalid_model_json_fails_closed_and_emits_error_telemetry():
    emitted = []
    client = TensorMuxClient(
        _settings(max_retries=0),
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"choices": [{"message": {"content": "not-json"}}]}
                )
            )
        ),
        telemetry_sink=emitted.append,
    )
    with pytest.raises(TensorMuxError, match="Invalid structured") as caught:
        client.generate_structured(
            EvidencePrompt(task=AgentTask.EXTRACTION, expected_schema={}, evidence=[]),
            InvestigationOutput,
        )
    assert caught.value.telemetry.status == "error"
    assert caught.value.telemetry.retry_count == 0
    assert emitted[0].status == "error"
