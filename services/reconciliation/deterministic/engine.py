from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from itertools import combinations
from uuid import UUID

from packages.contracts import (
    Allocation,
    AuditEvent,
    FinancialRecord,
    MatchReasonCode,
    MatchResult,
    ReconciliationStatus,
)

DEFAULT_DATE_WINDOW_DAYS = 3
DEFAULT_MAX_ALLOCATION_GROUP_SIZE = 4


@dataclass(frozen=True)
class ReconciliationStage:
    """One deterministic edge in a configured reconciliation graph."""

    name: str
    sources: Sequence[FinancialRecord]
    targets: Sequence[FinancialRecord]
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS
    max_allocation_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE


@dataclass
class ReconciliationRun:
    """Results and audit events for a deterministic reconciliation workflow."""

    results: dict[str, list[MatchResult]] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)

    @property
    def all_results(self) -> list[MatchResult]:
        return [result for stage in self.results.values() for result in stage]


def match_pair(
    source: FinancialRecord,
    target: FinancialRecord,
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
) -> MatchResult:
    """Evaluate one source/target pair using deterministic rules only."""
    source_currency = source.currency.upper()
    target_currency = target.currency.upper()
    if source_currency != target_currency:
        return MatchResult(
            source_record_ids=[source.id],
            target_record_ids=[target.id],
            status=ReconciliationStatus.EXCEPTION,
            confidence=Decimal(0),
            reason_codes=[MatchReasonCode.CURRENCY_MISMATCH],
        )

    reasons: list[MatchReasonCode] = [MatchReasonCode.CURRENCY_MATCH]
    if _same_reference(source, target):
        reasons.insert(0, MatchReasonCode.EXACT_REFERENCE)
        return _matched(source, target, reasons, Decimal("1.00"))
    if _same_external_id(source, target):
        reasons.insert(0, MatchReasonCode.EXACT_ID)
        return _matched(source, target, reasons, Decimal("1.00"))

    amount_delta = abs(source.amount - target.amount)
    if amount_delta == 0:
        reasons.insert(0, MatchReasonCode.EXACT_AMOUNT)
        day_delta = abs((source.record_date - target.record_date).days)
        if day_delta == 0:
            return _matched(source, target, reasons, Decimal("0.95"))
        if day_delta <= date_window_days:
            reasons.insert(1, MatchReasonCode.KNOWN_TIMING)
            reasons.insert(1, MatchReasonCode.AMOUNT_DATE_WINDOW)
            return _matched(source, target, reasons, Decimal("0.90"))

    fee_amount = _fee_amount(source, target)
    if fee_amount is not None and amount_delta == fee_amount:
        reasons.insert(0, MatchReasonCode.KNOWN_FEE)
        return MatchResult(
            source_record_ids=[source.id],
            target_record_ids=[target.id],
            status=ReconciliationStatus.EXCEPTION,
            confidence=Decimal("0.90"),
            reason_codes=reasons,
        )

    return MatchResult(
        source_record_ids=[source.id],
        target_record_ids=[target.id],
        status=ReconciliationStatus.UNMATCHED,
        confidence=Decimal(0),
        reason_codes=[MatchReasonCode.UNMATCHED],
    )


def reconcile_records(
    sources: Iterable[FinancialRecord],
    targets: Iterable[FinancialRecord],
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    max_allocation_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE,
) -> list[MatchResult]:
    """Reconcile records deterministically with stable one-to-one assignment.

    Inputs are sorted by UUID before assignment so duplicate candidates produce the
    same result across runs. Unmatched records are retained in the output.
    """
    source_records = sorted(sources, key=lambda record: str(record.id))
    target_records = sorted(targets, key=lambda record: str(record.id))
    results: list[MatchResult] = []
    used_targets: set[UUID] = set()
    matched_sources: set[UUID] = set()

    for source in source_records:
        candidates = [
            match_pair(source, target, date_window_days=date_window_days)
            for target in target_records
            if target.id not in used_targets
        ]
        viable = [
            candidate
            for candidate in candidates
            if candidate.status in {ReconciliationStatus.MATCHED, ReconciliationStatus.EXCEPTION}
        ]
        if viable:
            selected = max(
                viable,
                key=lambda candidate: (candidate.confidence, str(candidate.target_record_ids[0])),
            )
            results.append(selected)
            matched_sources.add(source.id)
            used_targets.update(selected.target_record_ids)
            continue

        allocation = allocate_one_to_many(
            source,
            [target for target in target_records if target.id not in used_targets],
            max_group_size=max_allocation_group_size,
        )
        if allocation is not None:
            results.append(allocation)
            matched_sources.add(source.id)
            used_targets.update(allocation.target_record_ids)
            continue

        results.append(
            MatchResult(
                source_record_ids=[source.id],
                status=ReconciliationStatus.UNMATCHED,
                reason_codes=[MatchReasonCode.UNMATCHED],
            )
        )

    for target in target_records:
        if target.id not in used_targets:
            results.append(
                MatchResult(
                    source_record_ids=[],
                    target_record_ids=[target.id],
                    status=ReconciliationStatus.UNMATCHED,
                    reason_codes=[MatchReasonCode.UNMATCHED],
                )
            )
    return results


def reconcile_configured_graph(stages: Iterable[ReconciliationStage]) -> ReconciliationRun:
    """Run a deterministic, ordered set of configured source-to-target stages."""
    run = ReconciliationRun()
    for stage in stages:
        if stage.name in run.results:
            raise ValueError(f"Duplicate reconciliation stage: {stage.name}")
        stage_results = reconcile_records(
            stage.sources,
            stage.targets,
            date_window_days=stage.date_window_days,
            max_allocation_group_size=stage.max_allocation_group_size,
        )
        run.results[stage.name] = stage_results
        run.audit_events.extend(audit_events_for_results(stage_results))
    return run


def reconcile_bank(
    bank_transactions: Iterable[FinancialRecord],
    ledger_entries: Iterable[FinancialRecord],
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    max_allocation_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE,
) -> ReconciliationRun:
    """Reconcile bank activity to the cash ledger, including outstanding items."""
    return reconcile_configured_graph(
        [
            ReconciliationStage(
                "bank_to_ledger",
                list(bank_transactions),
                list(ledger_entries),
                date_window_days,
                max_allocation_group_size,
            )
        ]
    )


def reconcile_vendor(
    purchase_orders: Iterable[FinancialRecord],
    invoices: Iterable[FinancialRecord],
    ap_entries: Iterable[FinancialRecord],
    payments: Iterable[FinancialRecord],
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    max_allocation_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE,
) -> ReconciliationRun:
    """Reconcile the vendor chain PO -> invoice -> AP -> payment."""
    return reconcile_configured_graph(
        [
            ReconciliationStage(
                "purchase_order_to_invoice",
                list(purchase_orders),
                list(invoices),
                date_window_days,
                max_allocation_group_size,
            ),
            ReconciliationStage(
                "invoice_to_ap",
                list(invoices),
                list(ap_entries),
                date_window_days,
                max_allocation_group_size,
            ),
            ReconciliationStage(
                "ap_to_payment",
                list(ap_entries),
                list(payments),
                date_window_days,
                max_allocation_group_size,
            ),
        ]
    )


def reconcile_customer(
    invoices: Iterable[FinancialRecord],
    receipts: Iterable[FinancialRecord],
    ar_entries: Iterable[FinancialRecord],
    *,
    date_window_days: int = DEFAULT_DATE_WINDOW_DAYS,
    max_allocation_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE,
) -> ReconciliationRun:
    """Reconcile the customer chain invoice -> receipt -> AR."""
    return reconcile_configured_graph(
        [
            ReconciliationStage(
                "invoice_to_receipt",
                list(invoices),
                list(receipts),
                date_window_days,
                max_allocation_group_size,
            ),
            ReconciliationStage(
                "receipt_to_ar",
                list(receipts),
                list(ar_entries),
                date_window_days,
                max_allocation_group_size,
            ),
        ]
    )


def allocate_one_to_many(
    source: FinancialRecord,
    targets: Iterable[FinancialRecord],
    *,
    max_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE,
) -> MatchResult | None:
    """Find a same-currency target subset whose Decimal total equals the source."""
    target_records = sorted(targets, key=lambda record: str(record.id))
    for group_size in range(2, max_group_size + 1):
        for group in combinations(target_records, group_size):
            if not _same_currency(source, group):
                continue
            if sum((record.amount for record in group), Decimal(0)) != source.amount:
                continue
            allocations = [
                Allocation(
                    source_record_id=source.id,
                    target_record_id=target.id,
                    amount=target.amount,
                    currency=source.currency.upper(),
                )
                for target in group
            ]
            return MatchResult(
                source_record_ids=[source.id],
                target_record_ids=[target.id for target in group],
                status=ReconciliationStatus.MATCHED,
                confidence=Decimal("0.88"),
                reason_codes=[MatchReasonCode.EXACT_AMOUNT],
                allocations=allocations,
            )
    return None


def allocate_many_to_one(
    sources: Iterable[FinancialRecord],
    target: FinancialRecord,
    *,
    max_group_size: int = DEFAULT_MAX_ALLOCATION_GROUP_SIZE,
) -> MatchResult | None:
    """Find a same-currency source subset whose Decimal total equals the target."""
    source_records = sorted(sources, key=lambda record: str(record.id))
    for group_size in range(2, max_group_size + 1):
        for group in combinations(source_records, group_size):
            if not _same_currency(target, group):
                continue
            if sum((record.amount for record in group), Decimal(0)) != target.amount:
                continue
            allocations = [
                Allocation(
                    source_record_id=source.id,
                    target_record_id=target.id,
                    amount=source.amount,
                    currency=target.currency.upper(),
                )
                for source in group
            ]
            return MatchResult(
                source_record_ids=[source.id for source in group],
                target_record_ids=[target.id],
                status=ReconciliationStatus.MATCHED,
                confidence=Decimal("0.88"),
                reason_codes=[MatchReasonCode.EXACT_AMOUNT],
                allocations=allocations,
            )
    return None


def audit_events_for_results(
    results: Iterable[MatchResult],
    *,
    actor: str = "deterministic_reconciliation",
) -> list[AuditEvent]:
    """Create audit events for persisted reconciliation decisions."""
    events: list[AuditEvent] = []
    for result in results:
        entity_id = (
            result.source_record_ids[0]
            if result.source_record_ids
            else result.target_record_ids[0]
        )
        events.append(
            AuditEvent(
                event_type="RECONCILIATION_DECISION",
                actor=actor,
                entity_type="ReconciliationItem",
                entity_id=entity_id,
                occurred_at=datetime.now(UTC),
                details={
                    "source_record_ids": [str(record_id) for record_id in result.source_record_ids],
                    "target_record_ids": [str(record_id) for record_id in result.target_record_ids],
                    "status": result.status.value,
                    "reason_codes": [reason.value for reason in result.reason_codes],
                },
            )
        )
    return events


def _matched(
    source: FinancialRecord,
    target: FinancialRecord,
    reasons: list[MatchReasonCode],
    confidence: Decimal,
) -> MatchResult:
    return MatchResult(
        source_record_ids=[source.id],
        target_record_ids=[target.id],
        status=ReconciliationStatus.MATCHED,
        confidence=confidence,
        reason_codes=reasons,
    )


def _same_external_id(source: FinancialRecord, target: FinancialRecord) -> bool:
    return bool(
        source.external_id
        and target.external_id
        and source.external_id == target.external_id
    )


def _same_reference(source: FinancialRecord, target: FinancialRecord) -> bool:
    source_references = _references(source)
    target_references = _references(target)
    return bool(source_references & target_references)


def _references(record: FinancialRecord) -> set[str]:
    fields = (
        "bank_reference",
        "payment_reference",
        "settlement_reference",
        "invoice_number",
    )
    return {
        str(value).strip().casefold()
        for field in fields
        if (value := getattr(record, field, None))
    }


def _fee_amount(source: FinancialRecord, target: FinancialRecord) -> Decimal | None:
    for record in (source, target):
        fee_amount = getattr(record, "fee_amount", None)
        if fee_amount is not None and fee_amount != 0:
            return abs(fee_amount)
    return None


def _same_currency(record: FinancialRecord, group: Iterable[FinancialRecord]) -> bool:
    return all(record.currency.upper() == member.currency.upper() for member in group)
