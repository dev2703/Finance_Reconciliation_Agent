"""OpenAI-compatible TensorMux client with strict outputs and call telemetry."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from packages.contracts.models import ContractModel
from services.agents.prompts import EvidencePrompt, build_messages


class TensorMuxSettings(BaseSettings):
    """Gateway settings. Secrets are loaded from the environment and never serialized."""

    model_config = SettingsConfigDict(env_prefix="TENSORMUX_", extra="ignore")

    base_url: str = "http://localhost:8080/v1"
    api_key: SecretStr
    model: str = "glm-4-7b-flash"
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    max_retries: int = Field(default=2, ge=0, le=5)
    input_cost_per_million: Decimal = Field(default=Decimal(0), ge=0)
    output_cost_per_million: Decimal = Field(default=Decimal(0), ge=0)


class ModelCallTelemetry(ContractModel):
    model: str
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(ge=0)
    retry_count: int = Field(ge=0)
    status: str
    estimated_cost: Decimal = Field(default=Decimal(0), ge=0)
    case_id: str | None = None
    agent_run_id: str | None = None


class StructuredModelResult[OutputT: ContractModel](ContractModel):
    output: OutputT
    telemetry: ModelCallTelemetry


class TensorMuxError(RuntimeError):
    def __init__(self, message: str, telemetry: ModelCallTelemetry) -> None:
        super().__init__(message)
        self.telemetry = telemetry


class TensorMuxClient:
    """Small synchronous adapter around TensorMux's OpenAI-compatible endpoint."""

    _RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: TensorMuxSettings,
        *,
        http_client: httpx.Client | None = None,
        telemetry_sink: Callable[[ModelCallTelemetry], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=settings.timeout_seconds)
        self._telemetry_sink = telemetry_sink
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> TensorMuxClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def generate_structured[OutputT: ContractModel](
        self,
        prompt: EvidencePrompt,
        output_type: type[OutputT],
        *,
        case_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> StructuredModelResult[OutputT]:
        payload = {
            "model": self.settings.model,
            "messages": build_messages(prompt),
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output_type.__name__,
                    "strict": True,
                    "schema": output_type.model_json_schema(),
                },
            },
        }
        started = time.monotonic()
        last_error = "TensorMux request failed"
        attempts = self.settings.max_retries + 1

        for attempt in range(attempts):
            try:
                response = self._http.post(
                    f"{self.settings.base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=self.settings.timeout_seconds,
                )
                if response.status_code in self._RETRYABLE_STATUS and attempt + 1 < attempts:
                    last_error = f"TensorMux returned HTTP {response.status_code}"
                    self._sleep(0.25 * (2**attempt))
                    continue
                response.raise_for_status()
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if isinstance(content, str):
                    content = json.loads(content)
                output = output_type.model_validate(content)
                telemetry = self._telemetry(
                    body, started, attempt, "success", case_id, agent_run_id
                )
                self._emit(telemetry)
                return StructuredModelResult(output=output, telemetry=telemetry)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = str(exc)
                retryable = isinstance(exc, httpx.TransportError) or (
                    exc.response.status_code in self._RETRYABLE_STATUS
                )
                if retryable and attempt + 1 < attempts:
                    self._sleep(0.25 * (2**attempt))
                    continue
                break
            except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
                last_error = f"Invalid structured TensorMux response: {exc}"
                break

        telemetry = self._telemetry({}, started, attempt, "error", case_id, agent_run_id)
        self._emit(telemetry)
        raise TensorMuxError(last_error, telemetry)

    def _telemetry(
        self,
        body: dict[str, Any],
        started: float,
        retries: int,
        status: str,
        case_id: str | None,
        agent_run_id: str | None,
    ) -> ModelCallTelemetry:
        usage = body.get("usage", {})
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        cost = (
            Decimal(prompt_tokens) * self.settings.input_cost_per_million
            + Decimal(completion_tokens) * self.settings.output_cost_per_million
        ) / Decimal(1_000_000)
        return ModelCallTelemetry(
            model=self.settings.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
            retry_count=retries,
            status=status,
            estimated_cost=cost,
            case_id=case_id,
            agent_run_id=agent_run_id,
        )

    def _emit(self, telemetry: ModelCallTelemetry) -> None:
        if self._telemetry_sink:
            self._telemetry_sink(telemetry)
