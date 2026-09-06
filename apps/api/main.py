from datetime import date
from decimal import Decimal

from fastapi import FastAPI

from packages.contracts import Invoice

app = FastAPI(title="Finance Reconciliation API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/contracts/sample", response_model=Invoice)
def sample_invoice() -> Invoice:
    return Invoice(
        invoice_number="INV-1001",
        amount=Decimal("1200.00"),
        currency="USD",
        record_date=date(2026, 1, 15),
        vendor_id="vendor-42",
        tax_amount=Decimal("100.00"),
    )
