from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from packages.contracts.models import Invoice, LedgerEntry
from services.agents.runtime import InvestigationBudget, InvestigationLimits
from services.agents.tools import (
    ReadOnlyRecordTools,
    calculate_variance,
    validate_conservation,
    validate_journal,
)


def test_read_only_tools_search_and_return_only_expected_record_type():
    invoice = Invoice(
        invoice_number="INV-1",
        amount=Decimal("10.00"),
        currency="USD",
        record_date=date.today(),
        description="Acme subscription",
        metadata={"payment_id": "pay-1"},
    )
    tools = ReadOnlyRecordTools([invoice])
    assert tools.search_records("acme") == [invoice]
    assert tools.get_invoice(invoice.id) == invoice
    assert tools.get_payment(invoice.id) is None
    assert tools.get_related_records(invoice.id) == []


def test_deterministic_financial_tools_use_exact_decimal_arithmetic():
    assert calculate_variance(Decimal("10.00"), Decimal("9.90")) == Decimal("0.10")
    assert validate_conservation([Decimal("10.00")], [Decimal("3.00"), Decimal("7.00")])
    entry = LedgerEntry(
        journal_id="j-1",
        account_code="100",
        amount=Decimal(10),
        currency="USD",
        record_date=date.today(),
        debit=Decimal(10),
        credit=Decimal(10),
    )
    assert validate_journal([entry])


def test_investigation_budget_rejects_duplicate_and_over_budget_calls():
    budget = InvestigationBudget(
        InvestigationLimits(max_llm_turns=1, max_tool_calls=1, max_context_bytes=20)
    )
    budget.register_turn()
    with pytest.raises(RuntimeError, match="turn limit"):
        budget.register_turn()
    budget.register_tool_call("get_invoice", {"id": "a"}, {"amount": "1"})
    with pytest.raises(RuntimeError, match="Duplicate"):
        budget.register_tool_call("get_invoice", {"id": "a"}, {"amount": "1"})
