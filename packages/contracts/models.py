from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FinancialRecord(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    external_id: str | None = None
    amount: Decimal
    currency: str = Field(min_length=3, max_length=3)
    record_date: date
    description: str | None = None
    source_document_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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


class ReconciliationItem(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    source_record_ids: list[UUID] = Field(min_length=1)
    target_record_ids: list[UUID] = Field(default_factory=list)
    status: ReconciliationStatus
    confidence: Decimal = Field(default=Decimal(0), ge=0, le=1)
    reason_codes: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


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
