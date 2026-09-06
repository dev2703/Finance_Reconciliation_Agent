"""Report assembly from supplied, already-computed metrics and audit events."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from packages.contracts.models import AuditEvent, ReconciliationItem, ReconciliationStatus


def build_operational_reports(
    items: Sequence[ReconciliationItem],
    audit_events: Sequence[AuditEvent],
    *,
    pending_reviews: int = 0,
) -> dict[str, dict[str, Any]]:
    """Build reconciliation, exception, audit, and automation reports deterministically."""
    total = len(items)
    matched = sum(item.status is ReconciliationStatus.MATCHED for item in items)
    exceptions = [item for item in items if item.status is ReconciliationStatus.EXCEPTION]
    automated = sum(
        event.event_type in {"AUTO_APPROVED", "AUTO_RECONCILED"} for event in audit_events
    )
    rate = Decimal(matched) / Decimal(total) if total else Decimal(0)
    automation_rate = Decimal(automated) / Decimal(total) if total else Decimal(0)
    return {
        "reconciliation": {
            "item_count": total,
            "matched_count": matched,
            "reconciliation_rate": format(rate, "f"),
        },
        "exceptions": {
            "exception_count": len(exceptions),
            "item_ids": [str(item.id) for item in exceptions],
        },
        "audit": {
            "event_count": len(audit_events),
            "event_types": [event.event_type for event in audit_events],
        },
        "automation": {
            "automated_count": automated,
            "automation_rate": format(automation_rate, "f"),
            "pending_reviews": pending_reviews,
        },
    }
