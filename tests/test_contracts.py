import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from packages.contracts import Invoice, Payment


def test_sample_fixture_loads_into_canonical_models() -> None:
    fixture = json.loads(
        (Path(__file__).parents[1] / "packages/contracts/fixtures/sample_records.json").read_text()
    )

    invoice = Invoice.model_validate(fixture["invoice"])
    payment = Payment.model_validate(fixture["payment"])

    assert invoice.amount == Decimal("1200.00")
    assert invoice.record_date == date(2026, 1, 15)
    assert payment.payment_reference == "PAY-1001"


def test_money_is_serialized_without_float_conversion() -> None:
    invoice = Invoice(
        invoice_number="INV-1",
        amount=Decimal("0.10"),
        currency="USD",
        record_date=date(2026, 1, 1),
    )

    assert invoice.model_dump(mode="json")["amount"] == "0.10"
