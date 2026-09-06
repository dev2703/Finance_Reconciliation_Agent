"""Deterministic pre-posting validation. No accounting state is mutated here."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .engine import PolicyDecision


@dataclass(frozen=True)
class JournalLine:
    account_code: str
    debit: Decimal = Decimal(0)
    credit: Decimal = Decimal(0)
    currency: str = "USD"


@dataclass(frozen=True)
class JournalProposal:
    idempotency_key: str
    period: date
    lines: tuple[JournalLine, ...]
    source_records_valid: bool
    already_reconciled: bool = False
    llm_generated: bool = False


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason_codes: tuple[str, ...] = ()


@dataclass
class AccountingValidator:
    closed_periods: set[tuple[int, int]] = field(default_factory=set)
    executed_keys: set[str] = field(default_factory=set)

    def validate(self, proposal: JournalProposal, policy: PolicyDecision) -> ValidationResult:
        reasons: list[str] = []
        if policy not in {PolicyDecision.AUTO_APPROVE, PolicyDecision.HUMAN_REVIEW}:
            reasons.append("POLICY_DISALLOWS_ACTION")
        if not proposal.idempotency_key.strip() or proposal.idempotency_key in self.executed_keys:
            reasons.append("DUPLICATE_ACTION")
        if (proposal.period.year, proposal.period.month) in self.closed_periods:
            reasons.append("CLOSED_PERIOD")
        if not proposal.source_records_valid:
            reasons.append("INVALID_SOURCE_RECORDS")
        if proposal.already_reconciled:
            reasons.append("ALREADY_RECONCILED")
        if proposal.llm_generated:
            reasons.append("LLM_GENERATED_JOURNAL_FORBIDDEN")
        if not proposal.lines:
            reasons.append("EMPTY_JOURNAL")
        currencies = {line.currency.upper() for line in proposal.lines}
        if len(currencies) != 1 or any(len(currency) != 3 for currency in currencies):
            reasons.append("INVALID_CURRENCY")
        debit = sum((line.debit for line in proposal.lines), Decimal(0))
        credit = sum((line.credit for line in proposal.lines), Decimal(0))
        if debit != credit:
            reasons.append("UNBALANCED_JOURNAL")
        if any(
            not line.account_code.strip()
            or line.debit < 0
            or line.credit < 0
            or (line.debit > 0 and line.credit > 0)
            or (line.debit == 0 and line.credit == 0)
            for line in proposal.lines
        ):
            reasons.append("INVALID_JOURNAL_LINE")
        return ValidationResult(not reasons, tuple(reasons))
