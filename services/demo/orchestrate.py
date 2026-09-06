"""Phase 18/20 demo orchestration: seed cases and run reconciliation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from packages.contracts import BankTransaction, LedgerEntry, ReconciliationStatus
from packages.contracts.models import FinancialRecord
from services.reconciliation.deterministic import reconcile_records


def financial_pairs_from_demo_cases(
    cases: list[dict[str, Any]],
) -> tuple[list[FinancialRecord], list[FinancialRecord]]:
    """Map the Phase 19 demo JSONL pack into bank/ledger records for matching."""
    sources: list[FinancialRecord] = []
    targets: list[FinancialRecord] = []
    for case in cases:
        truth = case["ground_truth"]
        label = case["label"]
        amount = Decimal(str(truth["amount"]))
        source_amount = amount
        target_amount = amount
        if label == "KNOWN_FEE":
            target_amount = amount - Decimal("2.50")
        elif label in {"PARTIAL_PAYMENT", "SPLIT_SETTLEMENT"}:
            target_amount = amount / Decimal(2)
        elif label == "WRONG_ALLOCATION":
            target_amount = amount + Decimal(10)
        elif label == "MISSING_BANK_TRANSACTION":
            targets.append(
                LedgerEntry(
                    id=uuid4(),
                    amount=amount,
                    currency="AUD",
                    record_date=date(2026, 1, 10),
                    journal_id=f"J-{case['case_id']}",
                    account_code="1000",
                    external_id=case["case_id"],
                    description=f"ledger:{case['case_id']}",
                )
            )
            continue
        elif label == "MISSING_LEDGER_TRANSACTION":
            sources.append(
                BankTransaction(
                    id=uuid4(),
                    amount=amount,
                    currency="AUD",
                    record_date=date(2026, 1, 10),
                    account_id="cash-1",
                    transaction_type="deposit",
                    bank_reference=f"REF-{case['case_id']}",
                    external_id=case["case_id"],
                    description=f"bank:{case['case_id']}",
                )
            )
            continue

        bank_reference = "REF-DUPLICATE" if label == "DUPLICATE" else f"REF-{case['case_id']}"
        shared_external = case["case_id"] if label in {"EXACT_MATCH", "HARD_NEGATIVE"} else None
        source = BankTransaction(
            id=uuid4(),
            amount=source_amount,
            currency="AUD",
            record_date=date(2026, 1, 10),
            account_id="cash-1",
            transaction_type="deposit",
            bank_reference=bank_reference,
            external_id=shared_external,
            description=label,
            metadata={"demo_case_id": case["case_id"], "label": label},
        )
        target = LedgerEntry(
            id=uuid4(),
            amount=target_amount,
            currency="AUD",
            record_date=date(2026, 1, 12) if label == "TIMING_DIFFERENCE" else date(2026, 1, 10),
            journal_id=f"J-{case['case_id']}",
            account_code="1000",
            external_id=shared_external,
            description=label,
            metadata={"demo_case_id": case["case_id"], "label": label},
        )
        sources.append(source)
        targets.append(target)
        if label == "DUPLICATE":
            sources.append(
                BankTransaction(
                    id=uuid4(),
                    amount=source_amount,
                    currency="AUD",
                    record_date=date(2026, 1, 10),
                    account_id="cash-1",
                    transaction_type="deposit",
                    bank_reference=bank_reference,
                    description=label,
                    metadata={"demo_case_id": case["case_id"], "label": label, "duplicate": True},
                )
            )
    return sources, targets


def run_reconciliation(
    sources: list[FinancialRecord],
    targets: list[FinancialRecord],
    *,
    date_window_days: int = 3,
) -> dict[str, Any]:
    """Execute deterministic reconciliation and split matched vs exception items."""
    results = reconcile_records(sources, targets, date_window_days=date_window_days)
    serialized = [result.model_dump(mode="json") for result in results]
    exceptions = [
        item
        for item in serialized
        if item["status"]
        in {ReconciliationStatus.EXCEPTION.value, ReconciliationStatus.UNMATCHED.value}
    ]
    matched = [item for item in serialized if item["status"] == ReconciliationStatus.MATCHED.value]
    return {
        "results": serialized,
        "exceptions": exceptions,
        "matched": matched,
        "matched_count": len(matched),
        "exception_count": len(exceptions),
    }
