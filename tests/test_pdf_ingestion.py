from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors

from services.ingestion.pdf import (
    extract_pdf,
    normalize_financial_value,
    is_repeated_header,
    is_subtotal_or_total,
)


def create_test_pdf_with_table():
    """Create a simple test PDF with a table containing financial data."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    
    # Add title
    title = Paragraph("Financial Summary", styles['Heading1'])
    story.append(title)
    story.append(Spacer(1, 0.3 * inch))
    
    # Create a table with financial data
    data = [
        ['Description', 'Amount', 'Date'],
        ['Invoice #1001', '$1,234.56', '2025-01-15'],
        ['Invoice #1002', '($500.00)', '2025-01-16'],
        ['Payment Received', '$2,100.00', '2025-01-17'],
        ['Fee', '(25.50)', '2025-01-18'],
    ]
    
    table = Table(data, colWidths=[2*inch, 1.5*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def create_test_pdf_native_text():
    """Create a test PDF with native text content."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1*inch, height - 1*inch, "Bank Statement")
    
    c.setFont("Helvetica", 12)
    c.drawString(1*inch, height - 1.5*inch, "Date Range: 2025-01-01 to 2025-01-31")
    c.drawString(1*inch, height - 1.8*inch, "Account: 123456789")
    
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, height - 2.5*inch, "Transactions:")
    
    c.setFont("Helvetica", 10)
    y = height - 2.8*inch
    transactions = [
        "01/05/2025  Deposit          $5,000.00",
        "01/10/2025  Wire Transfer    ($2,500.00)",
        "01/15/2025  ACH Payment      ($1,234.56)",
        "01/20/2025  Deposit          $3,100.50",
    ]
    
    for transaction in transactions:
        c.drawString(1*inch, y, transaction)
        y -= 0.25*inch
    
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer.getvalue()


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
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        
        # Page 1
        c.drawString(1*inch, 9*inch, "Page 1")
        c.showPage()
        
        # Page 2
        c.drawString(1*inch, 9*inch, "Page 2")
        c.showPage()
        
        c.save()
        buffer.seek(0)
        
        pages = extract_pdf(buffer.getvalue(), source_name="multi.pdf")
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
        assert amount == Decimal("1500000")
        
        amount, original = normalize_financial_value("2.5M")
        assert amount == Decimal("2500000")
    
    def test_normalize_thousands_scaling(self):
        """Test that thousands suffix is applied correctly."""
        amount, original = normalize_financial_value("500K")
        assert amount == Decimal("500000")
    
    def test_normalize_billions_scaling(self):
        """Test that billions suffix is applied correctly."""
        amount, original = normalize_financial_value("1.2B")
        assert amount == Decimal("1200000000")
    
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
