from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from observability import RunTrace, TraceEventType
from packages.contracts.models import AuditEvent, ReconciliationItem, ReconciliationStatus
from services.reporting import build_operational_reports


def test_run_trace_correlates_events_and_aggregates_model_telemetry():
    trace = RunTrace(case_id="case-1")
    trace.record(
        TraceEventType.MODEL_CALL,
        duration_ms=25,
        prompt_tokens=10,
        completion_tokens=5,
    )
    trace.record(TraceEventType.TOOL_CALL, duration_ms=3, details={"tool": "get_invoice"})
    trace.record(TraceEventType.RUN_COMPLETED)
    assert {event.run_id for event in trace.events} == {trace.run_id}
    assert trace.summary()["latency_ms"] == 28
    assert trace.summary()["prompt_tokens"] == 10
    with pytest.raises(RuntimeError, match="completed"):
        trace.record(TraceEventType.TOOL_CALL)


def test_operational_reports_use_supplied_results_without_llm_calculation():
    matched = ReconciliationItem(
        source_record_ids=[uuid4()], status=ReconciliationStatus.MATCHED
    )
    exception = ReconciliationItem(
        source_record_ids=[uuid4()], status=ReconciliationStatus.EXCEPTION
    )
    event = AuditEvent(
        event_type="AUTO_RECONCILED",
        actor="policy",
        entity_type="ReconciliationItem",
        entity_id=matched.id,
        occurred_at=datetime.now(UTC),
    )
    reports = build_operational_reports([matched, exception], [event], pending_reviews=1)
    assert reports["reconciliation"]["reconciliation_rate"] == "0.5"
    assert reports["exceptions"]["exception_count"] == 1
    assert reports["automation"] == {
        "automated_count": 1,
        "automation_rate": "0.5",
        "pending_reviews": 1,
    }
