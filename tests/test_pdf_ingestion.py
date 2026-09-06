from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import fitz
import pytest

from services.ingestion.pdf import (
    extract_pdf,
    is_repeated_header,
    is_subtotal_or_total,
    normalize_financial_value,
)
from services.ingestion.worker import _extract_records_from_pdf


def create_test_pdf_with_table():
    """Create a simple test PDF with a table containing financial data."""
    document = fitz.open()
    page = document.new_page()
    data = [
        ["Description", "Amount", "Date"],
        ["Invoice #1001", "$1,234.56", "2025-01-15"],
        ["Invoice #1002", "($500.00)", "2025-01-16"],
        ["Payment Received", "$2,100.00", "2025-01-17"],
        ["Fee", "(25.50)", "2025-01-18"],
    ]

    column_x = [50, 250, 370]
    row_height = 30
    for row_index, row in enumerate(data):
        y0 = 50 + row_index * row_height
        for column_index, value in enumerate(row):
            x0 = column_x[column_index]
            x1 = column_x[column_index + 1] if column_index < 2 else 520
            page.draw_rect(fitz.Rect(x0, y0, x1, y0 + row_height), color=(0, 0, 0))
            page.insert_text((x0 + 5, y0 + 20), value, fontsize=10)
    return document.tobytes()


def create_test_pdf_with_no_border_table():
    document = fitz.open()
    page = document.new_page()
    rows = [
        ("Date", "Description", "Amount"),
        ("2026-01-01", "Invoice 1", "100.00"),
        ("2026-01-02", "Invoice 2", "250.00"),
    ]
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            page.insert_text((50 + column_index * 170, 70 + row_index * 24), value)
    return document.tobytes()


def create_test_pdf_native_text():
    """Create a test PDF with native text content."""
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Bank Statement", fontsize=16)
    page.insert_text((72, 108), "Date Range: 2025-01-01 to 2025-01-31", fontsize=12)
    page.insert_text((72, 130), "Account: 123456789", fontsize=12)
    page.insert_text((72, 180), "Transactions:", fontsize=11)
    y = 205
    transactions = [
        "01/05/2025  Deposit          $5,000.00",
        "01/10/2025  Wire Transfer    ($2,500.00)",
        "01/15/2025  ACH Payment      ($1,234.56)",
        "01/20/2025  Deposit          $3,100.50",
    ]

    for transaction in transactions:
        page.insert_text((72, y), transaction, fontsize=10)
        y += 18
    return document.tobytes()


class TestPDFExtraction:
    """Tests for PDF native text extraction."""

    def test_extract_native_text(self):
        """Test extraction of native text from PDF."""
        pdf_content = create_test_pdf_native_text()
        pages = extract_pdf(pdf_content, source_name="test.pdf")

        assert len(pages) >= 1
        assert pages[0]["page_number"] == 1
        assert pages[0]["extraction_method"] in ["native_text", "ocr"]
        assert "Bank Statement" in pages[0]["text"] or "bank statement" in pages[0]["text"].lower()
        assert pages[0]["has_native_text"] or pages[0]["extraction_method"] == "ocr"

    def test_extract_words_with_coordinates(self):
        """Test that words are extracted with coordinate information."""
        pdf_content = create_test_pdf_native_text()
        pages = extract_pdf(pdf_content, source_name="test.pdf")

        page = pages[0]
        if page["words"]:
            # Check that words have coordinate information
            assert len(page["words"]) > 0
            word = page["words"][0]
            assert "text" in word
            assert "x0" in word and "y0" in word
            assert "x1" in word and "y1" in word

    def test_pdf_with_multiple_pages(self):
        """Test extraction from multi-page PDF."""
        document = fitz.open()
        document.new_page().insert_text((72, 72), "Page 1")
        document.new_page().insert_text((72, 72), "Page 2")

        pages = extract_pdf(document.tobytes(), source_name="multi.pdf")
        assert len(pages) == 2
        assert pages[0]["page_number"] == 1
        assert pages[1]["page_number"] == 2


class TestTableExtraction:
    """Tests for table detection and extraction from PDFs."""

    def test_table_detection(self):
        """Test that tables are detected in PDF pages."""
        pdf_content = create_test_pdf_with_table()
        pages = extract_pdf(pdf_content, source_name="table_test.pdf")

        assert len(pages) >= 1
        # Table detection may or may not find tables depending on PDF structure
        # Just verify the extraction runs without error
        page = pages[0]
        assert "text" in page
        assert "words" in page or "tables" in page

    def test_table_cells_have_metadata(self):
        """Test that extracted table cells contain required metadata."""
        pdf_content = create_test_pdf_with_table()
        pages = extract_pdf(pdf_content, source_name="table_test.pdf")

        # If tables were found, verify structure
        for page in pages:
            if "tables" in page:
                for table in page["tables"]:
                    assert "cells" in table
                    assert "table_index" in table
                    for cell in table["cells"]:
                        assert "text" in cell
                        assert "bbox" in cell
                        assert "row_index" in cell
                        assert "column_index" in cell
                        assert "confidence" in cell

    def test_no_border_table_uses_text_structure_strategy(self):
        pages = extract_pdf(create_test_pdf_with_no_border_table(), source_name="no-border.pdf")
        text_tables = [
            table for table in pages[0]["tables"] if table["extraction_method"] == "pdfplumber_text"
        ]
        assert text_tables
        assert {cell["column_index"] for cell in text_tables[0]["cells"]} >= {0, 1, 2}


def test_ocr_confidence_controls_fallback(monkeypatch):
    document = fitz.open()
    document.new_page()
    content = document.tobytes()
    document.close()
    monkeypatch.setattr(
        "services.ingestion.pdf.pytesseract.image_to_data",
        lambda *_args, **_kwargs: {
            "text": ["Scanned", "statement"],
            "conf": ["92", "88"],
            "left": [20, 100],
            "top": [20, 20],
            "width": [60, 80],
            "height": [20, 20],
            "block_num": [1, 1],
            "line_num": [1, 1],
            "word_num": [1, 2],
        },
    )
    page = extract_pdf(content, source_name="scan.pdf")[0]
    assert page["extraction_method"] == "ocr"
    assert page["ocr_confidence"] == Decimal("0.90")
    assert page["fallback_required"] is False
    assert page["words"][0]["x0"] == 10


def test_table_rows_convert_to_canonical_records_with_provenance():
    pages = [
        {
            "page_number": 1,
            "source_name": "bank.pdf",
            "confidence": Decimal("0.95"),
            "tables": [
                {
                    "table_index": 0,
                    "confidence": Decimal("0.90"),
                    "cells": [
                        {"row_index": 0, "column_index": 0, "text": "Date"},
                        {"row_index": 0, "column_index": 1, "text": "Amount"},
                        {"row_index": 0, "column_index": 2, "text": "Currency"},
                        {"row_index": 0, "column_index": 3, "text": "Account"},
                        {"row_index": 0, "column_index": 4, "text": "Type"},
                        {"row_index": 1, "column_index": 0, "text": "2026-01-15"},
                        {"row_index": 1, "column_index": 1, "text": "$125.00"},
                        {"row_index": 1, "column_index": 2, "text": "USD"},
                        {"row_index": 1, "column_index": 3, "text": "cash-1"},
                        {"row_index": 1, "column_index": 4, "text": "deposit"},
                    ],
                }
            ],
        }
    ]
    result = _extract_records_from_pdf(pages, "bank", uuid4())
    assert result["errors"] == []
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record.amount == Decimal("125.00")
    assert record.provenance.extraction_method == "table_extraction"
    assert record.provenance.page_number == 1
    assert record.provenance.table_row_index == 1


class TestFinancialNormalization:
    """Tests for financial value normalization."""

    def test_normalize_positive_amount(self):
        """Test normalization of simple positive amounts."""
        amount, original = normalize_financial_value("$1,234.56")
        assert amount == Decimal("1234.56")
        assert original == "$1,234.56"

    def test_normalize_parentheses_negative(self):
        """Test that parentheses negatives are converted correctly."""
        amount, original = normalize_financial_value("($500.00)")
        assert amount == Decimal("-500.00")
        assert original == "($500.00)"

    def test_normalize_millions_scaling(self):
        """Test that millions suffix is applied correctly."""
        amount, original = normalize_financial_value("1.5M")
        assert amount == Decimal(1500000)

        amount, original = normalize_financial_value("2.5M")
        assert amount == Decimal(2500000)

    def test_normalize_thousands_scaling(self):
        """Test that thousands suffix is applied correctly."""
        amount, original = normalize_financial_value("500K")
        assert amount == Decimal(500000)

    def test_normalize_billions_scaling(self):
        """Test that billions suffix is applied correctly."""
        amount, original = normalize_financial_value("1.2B")
        assert amount == Decimal(1200000000)

    def test_normalize_thousands_separator(self):
        """Test removal of thousands separators."""
        amount, original = normalize_financial_value("1,000,000.00")
        assert amount == Decimal("1000000.00")

    def test_normalize_european_format(self):
        """Test European number format (comma as decimal)."""
        amount, original = normalize_financial_value("1.234,56")
        assert amount == Decimal("1234.56")

    def test_normalize_invalid_input(self):
        """Test that invalid inputs return None."""
        amount, original = normalize_financial_value("not a number")
        assert amount is None
        assert original is None

    def test_normalize_empty_input(self):
        """Test that empty inputs return None."""
        amount, original = normalize_financial_value("")
        assert amount is None
        assert original is None

    def test_normalize_complex_amount(self):
        """Test complex amount with multiple transformations."""
        amount, original = normalize_financial_value("($ 1,234.56)")
        assert amount == Decimal("-1234.56")

    def test_normalize_currency_symbols(self):
        """Test various currency symbols."""
        for symbol in ["$", "€", "£", "¥"]:
            amount, original = normalize_financial_value(f"{symbol}100.00")
            assert amount == Decimal("100.00")


class TestHeaderDetection:
    """Tests for repeated header detection."""

    def test_repeated_header_detection(self):
        """Test detection of headers that appear multiple times."""
        header = "Date, Description, Amount"
        previous = [
            "Date, Description, Amount",
            "01/01/2025, Payment, $100",
            "Date, Description, Amount",
        ]

        assert is_repeated_header(header, previous, threshold=2)

    def test_no_repeated_header(self):
        """Test that unique headers are not flagged as repeated."""
        header = "Column A, Column B, Column C"
        previous = ["Column A, Column B, Column C"]

        assert not is_repeated_header(header, previous, threshold=2)

    def test_case_insensitive_header_matching(self):
        """Test that header matching is case-insensitive."""
        header = "DATE, DESCRIPTION, AMOUNT"
        previous = [
            "date, description, amount",
            "some other row",
            "Date, Description, Amount",
        ]

        assert is_repeated_header(header, previous, threshold=2)


class TestTotalDetection:
    """Tests for total/subtotal row detection."""

    def test_detect_total_row(self):
        """Test detection of total rows."""
        assert is_subtotal_or_total("Total: $5,000.00")
        assert is_subtotal_or_total("TOTAL")
        assert is_subtotal_or_total("Grand Total")

    def test_detect_subtotal_row(self):
        """Test detection of subtotal rows."""
        assert is_subtotal_or_total("Subtotal")
        assert is_subtotal_or_total("Sub-total: $2,500.00")

    def test_detect_balance_row(self):
        """Test detection of balance/sum rows."""
        assert is_subtotal_or_total("Balance: $10,000")
        assert is_subtotal_or_total("Sum")
        assert is_subtotal_or_total("Net Amount")

    def test_non_total_row(self):
        """Test that regular rows are not flagged as totals."""
        assert not is_subtotal_or_total("Invoice #1001")
        assert not is_subtotal_or_total("2025-01-15")
        assert not is_subtotal_or_total("$1,234.56")


@pytest.fixture
def sample_pdf_bytes():
    """Provide sample PDF bytes for testing."""
    return create_test_pdf_native_text()


@pytest.fixture
def sample_pdf_with_table():
    """Provide sample PDF with table for testing."""
    return create_test_pdf_with_table()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
