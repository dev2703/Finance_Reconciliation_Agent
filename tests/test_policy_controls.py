from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from packages.contracts import ProposedAction
from services.policy import (
    AccountingValidator,
    ApprovalPolicy,
    JournalLine,
    JournalProposal,
    PolicyContext,
    PolicyDecision,
)
from services.review import ReviewWorkflow


def test_policy_only_auto_approves_complete_low_value_exact_match() -> None:
    policy = ApprovalPolicy.default()
    result = policy.evaluate(
        PolicyContext(amount=Decimal(4999), exact_match=True, evidence_complete=True)
    )
    assert result.decision is PolicyDecision.AUTO_APPROVE
    assert (
        policy.evaluate(
            PolicyContext(amount=Decimal(5000), exact_match=True, evidence_complete=True)
        ).decision
        is PolicyDecision.HUMAN_REVIEW
    )
    assert (
        policy.evaluate(PolicyContext(amount=Decimal(1), unresolved=True)).decision
        is PolicyDecision.ESCALATE
    )


def test_missing_evidence_overrides_an_automation_rule() -> None:
    result = ApprovalPolicy.default().evaluate(
        PolicyContext(
            amount=Decimal(4),
            exact_match=True,
            evidence_complete=True,
            required_evidence=frozenset({"bank"}),
            supplied_evidence=frozenset(),
        )
    )
    assert result.decision is PolicyDecision.HUMAN_REVIEW
    assert result.reason_codes == ("MISSING_EVIDENCE",)


def test_accounting_validation_is_decimal_balanced_and_idempotent() -> None:
    validator = AccountingValidator(executed_keys={"done"})
    proposal = JournalProposal(
        "new",
        date(2026, 9, 1),
        (JournalLine("100", debit=Decimal(10)), JournalLine("200", credit=Decimal(10))),
        True,
    )
    assert validator.validate(proposal, PolicyDecision.AUTO_APPROVE).valid
    invalid = JournalProposal(
        "done",
        date(2026, 9, 1),
        (JournalLine("100", debit=Decimal(10)), JournalLine("200", credit=Decimal(9))),
        False,
        llm_generated=True,
    )
    reasons = validator.validate(invalid, PolicyDecision.AUTO_APPROVE).reason_codes
    assert {
        "DUPLICATE_ACTION",
        "INVALID_SOURCE_RECORDS",
        "UNBALANCED_JOURNAL",
        "LLM_GENERATED_JOURNAL_FORBIDDEN",
    } <= set(reasons)


def test_review_mutations_are_audited_and_single_decision() -> None:
    workflow = ReviewWorkflow()
    review_id = workflow.queue(
        ProposedAction(
            exception_case_id=uuid4(), action_type="WRITE_OFF", description="approved variance"
        ),
        PolicyDecision.HUMAN_REVIEW,
    )
    workflow.decide(
        review_id,
        PolicyDecision.REJECT,
        actor="controller",
        reason="insufficient evidence",
    )
    assert [event.event_type for event in workflow.audit_events] == [
        "REVIEW_QUEUED",
        "REVIEW_DECIDED",
    ]
    with pytest.raises(ValueError):
        workflow.decide(review_id, PolicyDecision.REJECT, actor="controller", reason="duplicate")
