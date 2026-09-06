"""Audited human approval decisions, deliberately separate from posting."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from packages.contracts import AuditEvent, ProposedAction
from services.audit import AuditWriter, mutation_event
from services.policy import PolicyDecision


@dataclass
class ReviewWorkflow:
    actions: dict[UUID, ProposedAction] = field(default_factory=dict)
    decisions: dict[UUID, PolicyDecision] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)
    audit_writer: AuditWriter | None = None

    def queue(
        self,
        action: ProposedAction,
        policy: PolicyDecision,
        *,
        actor: str = "policy_engine",
    ) -> UUID:
        if policy is not PolicyDecision.HUMAN_REVIEW:
            raise ValueError("Only human-review actions can enter the review workflow")
        review_id = uuid4()
        self.actions[review_id] = action
        self.decisions[review_id] = policy
        self._audit("REVIEW_QUEUED", actor, review_id, {"policy_decision": policy.value})
        return review_id

    def decide(
        self,
        review_id: UUID,
        decision: PolicyDecision,
        *,
        actor: str,
        reason: str,
    ) -> None:
        if decision not in {
            PolicyDecision.AUTO_APPROVE,
            PolicyDecision.REJECT,
            PolicyDecision.ESCALATE,
        }:
            raise ValueError("Review requires approve, reject, or escalate")
        if not actor.strip() or not reason.strip():
            raise ValueError("Review decision requires actor and reason")
        if review_id not in self.actions:
            raise KeyError(review_id)
        if self.decisions[review_id] is not PolicyDecision.HUMAN_REVIEW:
            raise ValueError(
                "Review has already been decided or is not awaiting human review"
            )
        self.decisions[review_id] = decision
        self._audit(
            "REVIEW_DECIDED", actor, review_id, {"decision": decision.value}, reason
        )

    def _audit(
        self,
        event_type: str,
        actor: str,
        review_id: UUID,
        details: dict[str, object],
        reason: str | None = None,
    ) -> None:
        event = mutation_event(
            event_type=event_type,
            actor=actor,
            entity_type="Review",
            entity_id=review_id,
            reason=reason,
            details=details,
        )
        self.audit_events.append(event)
        if self.audit_writer:
            self.audit_writer(event)
