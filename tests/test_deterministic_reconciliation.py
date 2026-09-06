from datetime import date, timedelta
from decimal import Decimal

from packages.contracts import (
    BankTransaction,
    LedgerEntry,
    MatchReasonCode,
    ReconciliationStatus,
    Settlement,
)
from services.reconciliation.deterministic import (
    ReconciliationStage,
    allocate_many_to_one,
    allocate_one_to_many,
    match_pair,
    reconcile_bank,
    reconcile_configured_graph,
    reconcile_customer,
    reconcile_records,
    reconcile_vendor,
)
from services.reconciliation.deterministic.engine import audit_events_for_results


def bank(amount: str, *, reference: str | None = None, days: int = 0, currency: str = "USD"):
    return BankTransaction(
        amount=Decimal(amount),
        currency=currency,
        record_date=date(2026, 1, 10) + timedelta(days=days),
        account_id="cash-1",
        transaction_type="deposit",
        bank_reference=reference,
    )


def ledger(amount: str, *, external_id: str | None = None, days: int = 0, currency: str = "USD"):
    return LedgerEntry(
        amount=Decimal(amount),
        currency=currency,
        record_date=date(2026, 1, 10) + timedelta(days=days),
        journal_id="J-1",
        account_code="1000",
        external_id=external_id,
    )


def test_exact_reference_match_emits_stable_reason_codes():
    target = Settlement(
        amount=Decimal("100.00"),
        currency="USD",
        record_date=date(2026, 1, 10),
        settlement_reference="WIRE-1",
    )
    result = match_pair(bank("100.00", reference="WIRE-1"), target)
    assert result.status == ReconciliationStatus.MATCHED
    assert result.reason_codes == [MatchReasonCode.EXACT_REFERENCE, MatchReasonCode.CURRENCY_MATCH]
    assert result.confidence == Decimal("1.00")


def test_exact_id_match():
    source = bank("100.00")
    target = ledger("25.00", external_id="shared-1")
    source.external_id = "shared-1"
    result = match_pair(source, target)
    assert result.status == ReconciliationStatus.MATCHED
    assert MatchReasonCode.EXACT_ID in result.reason_codes


def test_exact_amount_and_timing_match():
    result = match_pair(bank("100.00", days=2), ledger("100.00"))
    assert result.status == ReconciliationStatus.MATCHED
    assert MatchReasonCode.EXACT_AMOUNT in result.reason_codes
    assert MatchReasonCode.AMOUNT_DATE_WINDOW in result.reason_codes
    assert MatchReasonCode.KNOWN_TIMING in result.reason_codes


def test_currency_mismatch_is_not_silently_matched():
    result = match_pair(bank("100.00", currency="USD"), ledger("100.00", currency="EUR"))
    assert result.status == ReconciliationStatus.EXCEPTION
    assert result.reason_codes == [MatchReasonCode.CURRENCY_MISMATCH]


def test_known_fee_is_reported_as_exception():
    source = bank("100.00")
    target = Settlement(
        amount=Decimal("102.00"),
        currency="USD",
        record_date=date(2026, 1, 10),
        settlement_reference="SET-1",
        fee_amount=Decimal("2.00"),
    )
    result = match_pair(source, target)
    assert result.status == ReconciliationStatus.EXCEPTION
    assert result.reason_codes[0] == MatchReasonCode.KNOWN_FEE


def test_one_to_many_allocation_conserves_decimal_amount():
    source = bank("100.00")
    targets = [ledger("40.00"), ledger("60.00")]
    result = allocate_one_to_many(source, targets)
    assert result is not None
    assert result.status == ReconciliationStatus.MATCHED
    assert (
        sum((allocation.amount for allocation in result.allocations), Decimal(0))
        == source.amount
    )
    assert set(result.target_record_ids) == {target.id for target in targets}


def test_many_to_one_allocation_conserves_decimal_amount():
    sources = [bank("40.00"), bank("60.00")]
    target = ledger("100.00")
    result = allocate_many_to_one(sources, target)
    assert result is not None
    assert (
        sum((allocation.amount for allocation in result.allocations), Decimal(0))
        == target.amount
    )
    assert set(result.source_record_ids) == {source.id for source in sources}


def test_reconcile_records_applies_many_to_one_before_emitting_unmatched():
    sources = [bank("40.00"), bank("60.00")]
    target = ledger("100.00")
    results = reconcile_records(sources, [target])
    assert len(results) == 1
    assert results[0].status == ReconciliationStatus.MATCHED
    assert set(results[0].source_record_ids) == {source.id for source in sources}
    assert results[0].target_record_ids == [target.id]
    assert sum((row.amount for row in results[0].allocations), Decimal(0)) == target.amount


def test_reconcile_records_retains_unmatched_records_and_is_deterministic():
    source = bank("100.00", reference="REF-1")
    target = ledger("100.00")
    unmatched_target = ledger("12.00")
    first = reconcile_records([source], [target, unmatched_target])
    second = reconcile_records([source], [target, unmatched_target])
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]
    assert any(item.status == ReconciliationStatus.UNMATCHED for item in first)
    assert any(item.target_record_ids == [unmatched_target.id] for item in first)


def test_reconciliation_decisions_produce_audit_events():
    source = bank("100.00")
    target = ledger("100.00")
    results = reconcile_records([source], [target])
    events = audit_events_for_results(results)
    assert len(events) == 1
    assert events[0].event_type == "RECONCILIATION_DECISION"
    assert events[0].details["status"] == "MATCHED"


def test_bank_workflow_reports_outstanding_items_and_audits_each_decision():
    results = reconcile_bank([bank("100.00")], [ledger("100.00"), ledger("12.00")])

    assert set(results.results) == {"bank_to_ledger"}
    assert any(
        result.status == ReconciliationStatus.UNMATCHED
        and result.target_record_ids == [results.results["bank_to_ledger"][1].target_record_ids[0]]
        for result in results.results["bank_to_ledger"]
    )
    assert len(results.audit_events) == len(results.all_results)


def test_vendor_and_customer_workflows_expose_named_stages():
    vendor_record = ledger("100.00", external_id="vendor-1")
    vendor_run = reconcile_vendor(
        [vendor_record],
        [vendor_record],
        [vendor_record],
        [vendor_record],
    )
    customer_record = bank("100.00", reference="customer-1")
    customer_run = reconcile_customer(
        [customer_record],
        [customer_record],
        [customer_record],
    )

    assert set(vendor_run.results) == {
        "purchase_order_to_invoice",
        "invoice_to_ap",
        "ap_to_payment",
    }
    assert set(customer_run.results) == {"invoice_to_receipt", "receipt_to_ar"}
    assert all(run.audit_events for run in (vendor_run, customer_run))


def test_configured_graph_rejects_duplicate_stage_names():
    stage = ReconciliationStage("bank_to_ledger", [bank("10.00")], [ledger("10.00")])

    try:
        reconcile_configured_graph([stage, stage])
    except ValueError as exc:
        assert str(exc) == "Duplicate reconciliation stage: bank_to_ledger"
    else:
        raise AssertionError("duplicate stage names must be rejected")
