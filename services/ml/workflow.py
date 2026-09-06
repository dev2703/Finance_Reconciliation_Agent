"""End-to-end review-only integration for Phase 5 ML suggestions.

The workflow owns no accounting writer. Human decisions mutate only the proposal's
review state, and every such mutation emits an AuditEvent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from itertools import combinations
from pathlib import Path
from uuid import UUID, uuid4

from packages.contracts import AuditEvent, FinancialRecord
from services.reconciliation.graph import build_candidate_edges, build_entity_nodes

from .contracts import Candidate, ObservableRecord
from .model import rank_candidates

Ranker = Callable[[list[Candidate]], list[dict]]


class ReviewDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


@dataclass
class ReviewProposal:
    id: UUID
    candidate: Candidate
    probability: float
    model_version: str
    status: str = "PENDING_REVIEW"
    decision: ReviewDecision | None = None
    decision_reason: str | None = None


@dataclass(frozen=True)
class UnresolvedCandidate:
    candidate_id: str
    reason: str


@dataclass
class ReviewOutcome:
    candidates: list[Candidate]
    proposals: list[ReviewProposal]
    unresolved: list[UnresolvedCandidate]
    accounting_mutations: int = 0


@dataclass
class MLReviewWorkflow:
    """Generate the candidate universe, rank it once, and queue review proposals."""

    model_directory: Path | None = None
    ranker: Ranker | None = None
    proposals: dict[UUID, ReviewProposal] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)

    def suggest(
        self,
        records: Mapping[str, Iterable[FinancialRecord]],
        *,
        source_type: str,
        target_type: str,
        date_window_days: int = 3,
    ) -> ReviewOutcome:
        materialized = {name: list(values) for name, values in records.items()}
        candidates = generate_candidate_batch(
            materialized,
            source_type=source_type,
            target_type=target_type,
            date_window_days=date_window_days,
        )
        if not candidates:
            return ReviewOutcome(
                candidates=[],
                proposals=[],
                unresolved=[
                    UnresolvedCandidate(f"source:{record.id}", "NO_CANDIDATES")
                    for record in materialized.get(source_type, [])
                ],
            )

        # This is deliberately a single call with the complete blocked universe.
        ranked = self._rank(candidates)
        ranked_by_id = {row["candidate_id"]: row for row in ranked}
        if len(ranked) != len(candidates) or set(ranked_by_id) != {
            candidate.id for candidate in candidates
        }:
            raise ValueError("Ranker must return exactly one result for every candidate")
        if any(row.get("automatic_action_eligible") is not False for row in ranked):
            raise ValueError("ML ranker violated the review-only contract")

        allocation_ids = _allocation_candidate_ids(candidates)
        rival_counts = _rival_counts(candidates)
        proposals: list[ReviewProposal] = []
        unresolved: list[UnresolvedCandidate] = []
        for candidate in candidates:
            row = ranked_by_id[candidate.id]
            source_total, target_total = _totals(candidate)
            if candidate.id in allocation_ids:
                reason = "UNSUPPORTED_ALLOCATION"
            elif source_total != target_total:
                reason = "UNSUPPORTED_PARTIAL_PAYMENT"
            elif rival_counts[candidate.id] == 0:
                reason = "INSUFFICIENT_CANDIDATE_SET"
            elif row["suggestion"] != "REVIEW":
                reason = str(row["reason"])
            else:
                proposal = ReviewProposal(
                    id=uuid4(),
                    candidate=candidate,
                    probability=float(row["match_probability"]),
                    model_version=str(row["model_version"]),
                )
                self.proposals[proposal.id] = proposal
                self.audit_events.append(
                    AuditEvent(
                        event_type="ML_REVIEW_PROPOSAL_CREATED",
                        actor="ml_review_workflow",
                        entity_type="MLReviewProposal",
                        entity_id=proposal.id,
                        occurred_at=datetime.now(UTC),
                        details={
                            "candidate_id": proposal.candidate.id,
                            "accounting_state_mutated": False,
                            "model_version": proposal.model_version,
                        },
                    )
                )
                proposals.append(proposal)
                continue
            unresolved.append(UnresolvedCandidate(candidate.id, reason))
        return ReviewOutcome(candidates, proposals, unresolved)

    def decide(
        self,
        proposal_id: UUID,
        decision: ReviewDecision,
        *,
        actor: str,
        reason: str,
    ) -> ReviewProposal:
        if not actor.strip() or not reason.strip():
            raise ValueError("Review decisions require an actor and reason")
        proposal = self.proposals[proposal_id]
        if proposal.status != "PENDING_REVIEW":
            raise ValueError("Review proposal has already been decided")
        proposal.status = "REVIEW_DECIDED"
        proposal.decision = decision
        proposal.decision_reason = reason
        self.audit_events.append(
            AuditEvent(
                event_type="ML_REVIEW_DECISION",
                actor=actor,
                entity_type="MLReviewProposal",
                entity_id=proposal.id,
                occurred_at=datetime.now(UTC),
                reason=reason,
                details={
                    "candidate_id": proposal.candidate.id,
                    "decision": decision.value,
                    "accounting_state_mutated": False,
                    "model_version": proposal.model_version,
                },
            )
        )
        return proposal

    def _rank(self, candidates: list[Candidate]) -> list[dict]:
        if self.ranker is not None:
            return self.ranker(candidates)
        if self.model_directory is None:
            raise ValueError("A trusted model directory or ranker is required")
        return rank_candidates(self.model_directory, candidates)


def generate_candidate_batch(
    records: Mapping[str, list[FinancialRecord]],
    *,
    source_type: str,
    target_type: str,
    date_window_days: int = 3,
) -> list[Candidate]:
    """Build all graph-blocked cross-type pairs; callers cannot supply hand-picked pairs."""
    sources = records.get(source_type, [])
    targets = records.get(target_type, [])
    source_ids = {record.id for record in sources}
    target_ids = {record.id for record in targets}
    by_id = {record.id: record for record in sources + targets}
    nodes = build_entity_nodes({source_type: sources, target_type: targets})
    edges = build_candidate_edges(nodes, date_window_days=date_window_days)
    candidates = []
    for edge in edges:
        pair = {edge.source_node_id, edge.target_node_id}
        source_id = next((record_id for record_id in pair if record_id in source_ids), None)
        target_id = next((record_id for record_id in pair if record_id in target_ids), None)
        if source_id is None or target_id is None:
            continue
        source = _observable(by_id[source_id], source_type)
        target = _observable(by_id[target_id], target_type)
        candidates.append(
            Candidate(
                id=f"{source_id}:{target_id}",
                sources=[source],
                targets=[target],
                graph_score=edge.score,
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.id)


def _observable(record: FinancialRecord, record_type: str) -> ObservableRecord:
    reference = next(
        (
            str(value)
            for field_name in (
                "invoice_number",
                "payment_reference",
                "settlement_reference",
                "bank_reference",
                "external_id",
            )
            if (value := getattr(record, field_name, None))
        ),
        None,
    )
    party = next(
        (
            str(value)
            for field_name in ("vendor_id", "payer_id", "payee_id", "account_id")
            if (value := getattr(record, field_name, None))
        ),
        None,
    )
    return ObservableRecord(
        id=str(record.id),
        record_type=record_type,
        amount=record.amount,
        currency=record.currency.upper(),
        record_date=record.record_date,
        reference=reference,
        party=party,
        description=record.description,
    )


def _totals(candidate: Candidate) -> tuple[Decimal, Decimal]:
    return (
        sum((record.amount for record in candidate.sources), Decimal(0)),
        sum((record.amount for record in candidate.targets), Decimal(0)),
    )


def _rival_counts(candidates: list[Candidate]) -> dict[str, int]:
    resources = {
        candidate.id: {record.id for record in candidate.sources + candidate.targets}
        for candidate in candidates
    }
    return {
        candidate_id: sum(
            bool(record_ids & other_ids)
            for other_id, other_ids in resources.items()
            if other_id != candidate_id
        )
        for candidate_id, record_ids in resources.items()
    }


def _allocation_candidate_ids(candidates: list[Candidate]) -> set[str]:
    """Flag pair candidates participating in exact one-to-many/many-to-one totals."""
    by_source: dict[str, list[Candidate]] = {}
    by_target: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        by_source.setdefault(candidate.sources[0].id, []).append(candidate)
        by_target.setdefault(candidate.targets[0].id, []).append(candidate)
    unsupported: set[str] = set()
    for group in by_source.values():
        source_amount = group[0].sources[0].amount
        for size in range(2, min(4, len(group) + 1)):
            for selected in combinations(group, size):
                if sum((row.targets[0].amount for row in selected), Decimal(0)) == source_amount:
                    unsupported.update(row.id for row in selected)
    for group in by_target.values():
        target_amount = group[0].targets[0].amount
        for size in range(2, min(4, len(group) + 1)):
            for selected in combinations(group, size):
                if sum((row.sources[0].amount for row in selected), Decimal(0)) == target_amount:
                    unsupported.update(row.id for row in selected)
    return unsupported
