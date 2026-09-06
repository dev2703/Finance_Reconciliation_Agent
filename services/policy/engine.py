"""Configurable, deterministic approval policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class PolicyDecision(StrEnum):
    AUTO_APPROVE = "AUTO_APPROVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    REJECT = "REJECT"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class PolicyContext:
    amount: Decimal
    exact_match: bool = False
    known_variance: bool = False
    evidence_complete: bool = False
    unresolved: bool = False
    root_cause_confidence: Decimal | None = None
    required_evidence: frozenset[str] = frozenset()
    supplied_evidence: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PolicyRule:
    condition: dict[str, Any]
    action: PolicyDecision
    reason_codes: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    reason_codes: tuple[str, ...]
    required_evidence: tuple[str, ...]
    matched_rule: int | None


@dataclass
class ApprovalPolicy:
    """First matching rule wins; safe defaults ensure no accidental automation."""

    rules: list[PolicyRule] = field(default_factory=list)

    @classmethod
    def default(cls) -> ApprovalPolicy:
        return cls(
            rules=[
                PolicyRule({"unresolved": True}, PolicyDecision.ESCALATE, ("UNRESOLVED",)),
                PolicyRule(
                    {"amount_above": Decimal(5000)},
                    PolicyDecision.HUMAN_REVIEW,
                    ("HIGH_VALUE",),
                ),
                PolicyRule(
                    {"root_cause_confidence_below": Decimal("0.95")},
                    PolicyDecision.HUMAN_REVIEW,
                    ("LOW_ROOT_CAUSE_CONFIDENCE",),
                ),
                PolicyRule(
                    {
                        "exact_match": True,
                        "evidence_complete": True,
                        "amount_below": Decimal(5000),
                    },
                    PolicyDecision.AUTO_APPROVE,
                    ("EXACT_MATCH",),
                ),
                PolicyRule(
                    {
                        "known_variance": True,
                        "evidence_complete": True,
                        "amount_below": Decimal(5000),
                    },
                    PolicyDecision.AUTO_APPROVE,
                    ("KNOWN_VARIANCE",),
                ),
            ]
        )

    def evaluate(self, context: PolicyContext) -> PolicyResult:
        missing = tuple(sorted(context.required_evidence - context.supplied_evidence))
        if missing:
            return PolicyResult(PolicyDecision.HUMAN_REVIEW, ("MISSING_EVIDENCE",), missing, None)
        for index, rule in enumerate(self.rules):
            if _matches(rule.condition, context):
                return PolicyResult(rule.action, rule.reason_codes, rule.required_evidence, index)
        return PolicyResult(PolicyDecision.HUMAN_REVIEW, ("NO_AUTOMATION_RULE",), (), None)


def _matches(condition: dict[str, Any], context: PolicyContext) -> bool:
    for name, expected in condition.items():
        if name == "amount_below" and not context.amount < Decimal(str(expected)):
            return False
        if name == "amount_above" and not context.amount > Decimal(str(expected)):
            return False
        if name == "root_cause_confidence_below":
            if context.root_cause_confidence is None or context.root_cause_confidence >= Decimal(
                str(expected)
            ):
                return False
        if name not in {"amount_below", "amount_above", "root_cause_confidence_below"}:
            if getattr(context, name) != expected:
                return False
    return True
