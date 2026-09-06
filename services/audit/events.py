"""Deterministic audit-event construction for workflow mutations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from packages.contracts import AuditEvent

AuditWriter = Callable[[AuditEvent], None]


def mutation_event(
    *,
    event_type: str,
    actor: str,
    entity_type: str,
    entity_id: UUID,
    reason: str | None = None,
    details: dict[str, object] | None = None,
) -> AuditEvent:
    """Create the required audit record before a workflow mutation is returned."""
    if not event_type.strip() or not actor.strip() or not entity_type.strip():
        raise ValueError("Audit events require event type, actor, and entity type")
    return AuditEvent(
        event_type=event_type,
        actor=actor,
        entity_type=entity_type,
        entity_id=entity_id,
        occurred_at=datetime.now(UTC),
        reason=reason,
        details=details or {},
    )
