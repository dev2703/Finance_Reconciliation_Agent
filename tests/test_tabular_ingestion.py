from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from services.ingestion import (
    TabularParseError,
    parse_csv,
    parse_csv_result,
    parse_decimal,
    parse_xlsx,
)


def test_parse_decimal_supports_currency_and_parentheses() -> None:
    assert parse_decimal("($1,200.50)", field_name="amount") == Decimal("-1200.50")


def test_parse_csv_normalizes_records_and_preserves_provenance() -> None:
    content = (
        b"transaction id,total amount,transaction date,currency\n"
        b'TX-1,"1,200.50",2026-01-15,USD\n'
    )

    records = parse_csv(
        content,
        record_type="payment",
        source_name="bank.csv",
        column_mapping={"amount": "total amount"},
    )

    assert len(records) == 1
    assert records[0].amount == Decimal("1200.50")
    assert records[0].external_id == "TX-1"
    assert records[0].provenance.source_name == "bank.csv"
    assert records[0].provenance.row_number == 2
    assert records[0].provenance.original_fields["total amount"] == "1,200.50"


def test_parse_csv_rejects_unknown_record_types() -> None:
    with pytest.raises(TabularParseError, match="Unsupported record type"):
        parse_csv(
            b"amount,date\n10,2026-01-01\n",
            record_type="unknown",
            source_name="records.csv",
        )


def test_parse_xlsx_reads_multiple_sheets_and_provenance() -> None:
    workbook = Workbook()
    first_sheet = workbook.active
    first_sheet.title = "January"
    first_sheet.append(["invoice number", "amount", "date", "currency"])
    first_sheet.append(["INV-1", 100, "2026-01-01", "USD"])
    second_sheet = workbook.create_sheet("February")
    second_sheet.append(["invoice number", "amount", "date", "currency"])
    second_sheet.append(["INV-2", 200, "2026-02-01", "USD"])
    buffer = BytesIO()
    workbook.save(buffer)

    records = parse_xlsx(
        buffer.getvalue(),
        record_type="invoice",
        source_name="invoices.xlsx",
    )

    assert [record.invoice_number for record in records] == ["INV-1", "INV-2"]
    assert records[1].provenance.sheet == "February"
    assert records[1].provenance.row_number == 2


def test_parse_csv_result_keeps_valid_rows_and_reports_errors() -> None:
    result = parse_csv_result(
        b"invoice_number,amount,date,currency\nINV-1,10,2026-01-01,USD\nINV-2,bad,2026-01-02,USD\n",
        record_type="invoice",
        source_name="invoices.csv",
    )

    assert len(result.records) == 1
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3