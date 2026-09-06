from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field

from packages.contracts.models import ContractModel


class StructuredExtractionRequest(ContractModel):
    """Bounded input for structured extraction from one selected PDF page/crop."""

    page_number: int = Field(ge=1)
    page_crop: dict[str, float] | None = None
    tokens: list[dict[str, Any]] = Field(default_factory=list)
    cells: list[dict[str, Any]] = Field(default_factory=list)
    expected_schema: dict[str, str] = Field(default_factory=dict)


class StructuredExtractionResult(ContractModel):
    """Strict, auditable output from the extraction fallback boundary."""

    structured_data: dict[str, Any] = Field(default_factory=dict)
    confidence: Decimal = Field(default=Decimal(0), ge=0, le=1)
    unresolved_fields: list[str] = Field(default_factory=list)


def validate_structured_data(
    request: StructuredExtractionRequest,
    structured_data: dict[str, Any],
    *,
    confidence: Decimal = Decimal(1),
) -> StructuredExtractionResult:
    """Validate supplied extraction output without calling an LLM or a database.

    ``expected_schema`` maps field names to descriptive type names. Validation is
    intentionally bounded to declared fields; type coercion belongs to the
    deterministic financial normalizer.
    """
    allowed_fields = set(request.expected_schema)
    unexpected_fields = sorted(set(structured_data) - allowed_fields)
    if unexpected_fields:
        raise ValueError(f"Unexpected extraction fields: {', '.join(unexpected_fields)}")

    unresolved_fields = sorted(allowed_fields - set(structured_data))
    return StructuredExtractionResult(
        structured_data=dict(structured_data),
        confidence=confidence,
        unresolved_fields=unresolved_fields,
    )


def extract_structured_data(
    request: StructuredExtractionRequest,
    structured_data: dict[str, Any],
    *,
    confidence: Decimal = Decimal(1),
) -> StructuredExtractionResult:
    """Public bounded extraction tool contract.

    The current implementation validates caller-supplied structured output. It
    deliberately does not invoke a model or access application storage. A future
    model adapter must remain behind this same request/result boundary.
    """
    return validate_structured_data(request, structured_data, confidence=confidence)
