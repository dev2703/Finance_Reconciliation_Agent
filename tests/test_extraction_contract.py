from decimal import Decimal

import pytest

from services.agents.extraction import (
    StructuredExtractionRequest,
    extract_structured_data,
)


def test_bounded_extraction_returns_strict_structured_result():
    request = StructuredExtractionRequest(
        page_number=2,
        cells=[{"row_index": 1, "column_index": 0, "text": "100.00"}],
        expected_schema={"amount": "decimal", "currency": "string"},
    )
    result = extract_structured_data(
        request,
        {"amount": "100.00"},
        confidence=Decimal("0.72"),
    )
    assert result.structured_data == {"amount": "100.00"}
    assert result.confidence == Decimal("0.72")
    assert result.unresolved_fields == ["currency"]


def test_bounded_extraction_rejects_undeclared_fields():
    request = StructuredExtractionRequest(
        page_number=1,
        expected_schema={"amount": "decimal"},
    )
    with pytest.raises(ValueError, match="Unexpected extraction fields"):
        extract_structured_data(request, {"amount": "10", "account_id": "secret"})
