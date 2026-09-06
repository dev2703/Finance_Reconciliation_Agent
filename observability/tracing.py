"""Minimal local agent-run trace with stable correlation identifiers."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from packages.contracts.models import ContractModel


class TraceEventType(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    MODEL_CALL = "MODEL_CALL"
    TOOL_CALL = "TOOL_CALL"
    EVIDENCE = "EVIDENCE"
    DECISION = "DECISION"
    GUARDRAIL = "GUARDRAIL"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"


class TraceEvent(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    case_id: str | None = None
    event_type: TraceEventType
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int | None = Field(default=None, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


class RunTrace:
    """Append-only trace used even when Neatlogs is unavailable."""

    def __init__(self, *, run_id: UUID | None = None, case_id: str | None = None) -> None:
        self.run_id = run_id or uuid4()
        self.case_id = case_id
        self._events: list[TraceEvent] = []
        self.record(TraceEventType.RUN_STARTED)

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        return tuple(self._events)

    def record(
        self,
        event_type: TraceEventType,
        *,
        duration_ms: int | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        details: dict[str, Any] | None = None,
    ) -> TraceEvent:
        if self._events and self._events[-1].event_type in {
            TraceEventType.RUN_COMPLETED,
            TraceEventType.RUN_FAILED,
        }:
            raise RuntimeError("Cannot append to a completed trace")
        event = TraceEvent(
            run_id=self.run_id,
            case_id=self.case_id,
            event_type=event_type,
            duration_ms=duration_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            details=details or {},
        )
        self._events.append(event)
        return event

    def summary(self) -> dict[str, int | str]:
        return {
            "run_id": str(self.run_id),
            "event_count": len(self._events),
            "model_calls": sum(
                event.event_type is TraceEventType.MODEL_CALL for event in self._events
            ),
            "tool_calls": sum(
                event.event_type is TraceEventType.TOOL_CALL for event in self._events
            ),
            "prompt_tokens": sum(event.prompt_tokens for event in self._events),
            "completion_tokens": sum(event.completion_tokens for event in self._events),
            "latency_ms": sum(event.duration_ms or 0 for event in self._events),
        }
