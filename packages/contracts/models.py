from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Provenance(ContractModel):
    source_name: str
    source_type: str
    sheet: str | None = None
    row_number: int | None = Field(default=None, ge=1)
    original_fields: dict[str, str] = Field(default_factory=dict)
    extraction_method: str = "tabular"  # "tabular", "native_text", "ocr", "table_extraction"
    parser_confidence: Decimal = Field(default=Decimal(1), ge=0, le=1)
    transformation_history: list[str] = Field(default_factory=list)
    # PDF-specific fields
    page_number: int | None = Field(default=None, ge=1)
    table_index: int | None = Field(default=None, ge=0)
    table_row_index: int | None = Field(default=None, ge=0)
    table_column_index: int | None = Field(default=None, ge=0)
    bbox: dict[str, Any] | None = None  # {"x0": float, "y0": float, "x1": float, "y1": float}


class FinancialRecord(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    external_id: str | None = None
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    record_date: date
    description: str | None = None
    source_document_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(
        default_factory=lambda: Provenance(source_name="unknown", source_type="unknown")
    )


class Invoice(FinancialRecord):
    invoice_number: str
    vendor_id: str | None = None
    due_date: date | None = None
    tax_amount: Decimal = Decimal(0)


class Payment(FinancialRecord):
    payment_reference: str | None = None
    payer_id: str | None = None
    payee_id: str | None = None
    payment_method: str | None = None


class Settlement(FinancialRecord):
    settlement_reference: str
    processor: str | None = None
    fee_amount: Decimal = Decimal(0)
    settled_date: date | None = None


class BankTransaction(FinancialRecord):
    account_id: str
    transaction_type: str
    bank_reference: str | None = None
    value_date: date | None = None


class LedgerEntry(FinancialRecord):
    journal_id: str
    account_code: str
    debit: Decimal = Decimal(0)
    credit: Decimal = Decimal(0)
    posting_date: date | None = None


class Document(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    filename: str
    media_type: str
    sha256: str
    uploaded_at: datetime
    source: str
    page_count: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionStatus(StrEnum):
    UPLOADED = "UPLOADED"
    INGESTING = "INGESTING"
    PARSED = "PARSED"
    FAILED = "FAILED"
    CONFIRMED = "CONFIRMED"


class ParseError(ContractModel):
    row_number: int = Field(ge=1)
    sheet: str | None = None
    field: str | None = None
    original_value: str | None = None
    message: str


class EvidenceItem(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    document_id: UUID | None = None
    record_id: UUID | None = None
    locator: str
    excerpt: str
    confidence: Decimal = Field(default=Decimal(1), ge=0, le=1)


class ReconciliationStatus(StrEnum):
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    EXCEPTION = "EXCEPTION"


class MatchReasonCode(StrEnum):
    EXACT_REFERENCE = "exact_reference"
    EXACT_ID = "exact_id"
    EXACT_AMOUNT = "exact_amount"
    AMOUNT_DATE_WINDOW = "amount_date_window"
    CURRENCY_MATCH = "currency_match"
    CURRENCY_MISMATCH = "currency_mismatch"
    KNOWN_FEE = "known_fee"
    KNOWN_TIMING = "known_timing"
    UNMATCHED = "unmatched"
    DUPLICATE_CANDIDATE = "duplicate_candidate"


class Allocation(ContractModel):
    source_record_id: UUID
    target_record_id: UUID
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)


class MatchResult(ContractModel):
    source_record_ids: list[UUID] = Field(default_factory=list)
    target_record_ids: list[UUID] = Field(default_factory=list)
    status: ReconciliationStatus
    confidence: Decimal = Field(default=Decimal(0), ge=0, le=1)
    reason_codes: list[MatchReasonCode] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    allocations: list[Allocation] = Field(default_factory=list)


class ReconciliationItem(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    source_record_ids: list[UUID] = Field(min_length=1)
    target_record_ids: list[UUID] = Field(default_factory=list)
    status: ReconciliationStatus
    confidence: Decimal = Field(default=Decimal(0), ge=0, le=1)
    reason_codes: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    allocations: list[Allocation] = Field(default_factory=list)


class ExceptionCase(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    reconciliation_item_id: UUID
    title: str
    severity: str
    status: str = "OPEN"
    amount_at_risk: Decimal = Decimal(0)
    root_cause: str | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)


class ProposedAction(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    exception_case_id: UUID
    action_type: str
    description: str
    amount: Decimal | None = None
    currency: str | None = None
    requires_approval: bool = True


class Approval(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    proposed_action_id: UUID
    decision: str
    actor: str
    decided_at: datetime
    reason: str | None = None


class AuditEvent(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    event_type: str
    actor: str
    entity_type: str
    entity_id: UUID
    occurred_at: datetime
    reason: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# PHASE 4: Graph Reconciliation Schema
# ============================================================================


class EntityNode(ContractModel):
    """A node in the financial graph—a single record."""

    record_id: UUID
    record_type: str  # "invoice", "payment", "settlement", "bank_transaction", "ledger_entry", etc.
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    record_date: date
    normalized_party: str | None = None  # normalized vendor/payer/account identifier
    reference: str | None = None  # invoice number, check number, transaction ID, etc.
    amount_bucket: int | None = None  # for blocking: round(log10(amount)) * 10 for grouping
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateEdge(ContractModel):
    """A potential match between two nodes, scored but not yet ranked."""

    source_node_id: UUID
    target_node_id: UUID
    score: Decimal = Field(default=Decimal(0), ge=0, le=1)
    reason_codes: list[MatchReasonCode] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class GraphPath(ContractModel):
    """A complete lineage path through the financial graph."""

    node_ids: list[UUID]  # ordered sequence: source -> intermediate -> ... -> target
    edge_scores: list[Decimal] = Field(default_factory=list)  # score for each edge
    reason_code_sequence: list[list[MatchReasonCode]] = Field(default_factory=list)
    total_confidence: Decimal = Field(default=Decimal(0), ge=0, le=1)
    allocations: list[Allocation] = Field(default_factory=list)


class FinancialGraph(ContractModel):
    """A multi-hop reconciliation graph connecting all record types."""

    nodes: dict[UUID, EntityNode] = Field(default_factory=dict)
    candidate_edges: list[CandidateEdge] = Field(default_factory=list)
    selected_paths: list[GraphPath] = Field(default_factory=list)
    unmatched_node_ids: set[UUID] = Field(default_factory=set)
    blocked_edge_pairs: set[tuple[UUID, UUID]] = Field(default_factory=set)
