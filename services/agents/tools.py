"""Read-only evidence tools and deterministic financial checks for runtime agents."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any
from uuid import UUID

from packages.contracts.models import Document, FinancialRecord, LedgerEntry


class ReadOnlyRecordTools:
    """Small in-memory read model that can be replaced by a persistence adapter.

    Tool results are capped and expose canonical fields only. This layer deliberately
    has no create, update, execute, or arbitrary-query operation.
    """

    def __init__(
        self,
        records: Iterable[FinancialRecord] = (),
        documents: Iterable[Document] = (),
        *,
        max_results: int = 30,
    ) -> None:
        self._records = {record.id: record for record in records}
        self._documents = {document.id: document for document in documents}
        self._max_results = max_results

    def search_records(
        self, query: str, *, record_type: str | None = None
    ) -> list[FinancialRecord]:
        needle = query.casefold().strip()
        matches = (
            record
            for record in self._records.values()
            if (record_type is None or type(record).__name__.casefold() == record_type.casefold())
            and needle in self._record_search_text(record)
        )
        return list(matches)[: self._max_results]

    def get_related_records(self, record_id: UUID) -> list[FinancialRecord]:
        record = self._records.get(record_id)
        if record is None:
            return []
        related_ids = {
            str(value)
            for key, value in record.metadata.items()
            if key.endswith("_id") and value is not None
        }
        if record.external_id:
            related_ids.add(record.external_id)
        return [
            candidate
            for candidate in self._records.values()
            if candidate.id != record_id
            and related_ids.intersection(self._record_identifiers(candidate))
        ][: self._max_results]

    def get_record(self, record_id: UUID) -> FinancialRecord | None:
        return self._records.get(record_id)

    def get_invoice(self, record_id: UUID) -> FinancialRecord | None:
        return self._get_typed(record_id, "invoice")

    def get_payment(self, record_id: UUID) -> FinancialRecord | None:
        return self._get_typed(record_id, "payment")

    def get_settlement(self, record_id: UUID) -> FinancialRecord | None:
        return self._get_typed(record_id, "settlement")

    def get_bank_transaction(self, record_id: UUID) -> FinancialRecord | None:
        return self._get_typed(record_id, "banktransaction")

    def get_ledger_entry(self, record_id: UUID) -> FinancialRecord | None:
        return self._get_typed(record_id, "ledgerentry")

    def search_documents(self, query: str) -> list[Document]:
        needle = query.casefold().strip()
        return [
            document
            for document in self._documents.values()
            if needle in document.filename.casefold() or needle in document.source.casefold()
        ][: self._max_results]

    def get_document_page(self, document_id: UUID, page_number: int) -> dict[str, Any] | None:
        """Return bounded page metadata; bytes/content retrieval stays in the document service."""
        document = self._documents.get(document_id)
        if document is None or (document.page_count and page_number > document.page_count):
            return None
        return {
            "document_id": str(document_id),
            "page_number": page_number,
            "filename": document.filename,
        }

    def _get_typed(self, record_id: UUID, expected_type: str) -> FinancialRecord | None:
        record = self.get_record(record_id)
        return record if record and type(record).__name__.casefold() == expected_type else None

    @staticmethod
    def _record_search_text(record: FinancialRecord) -> str:
        values = [record.external_id, record.description, *map(str, record.metadata.values())]
        return " ".join(value for value in values if value).casefold()

    @staticmethod
    def _record_identifiers(record: FinancialRecord) -> set[str]:
        values = (str(value) for value in record.metadata.values() if value is not None)
        return {str(record.id), *values}


def calculate_variance(left: Decimal, right: Decimal) -> Decimal:
    """Return the exact signed monetary difference without floating-point arithmetic."""
    return left - right


def validate_conservation(
    source_amounts: Iterable[Decimal], target_amounts: Iterable[Decimal]
) -> bool:
    """Check whether allocation sides conserve value exactly."""
    return sum(source_amounts, Decimal(0)) == sum(target_amounts, Decimal(0))


def validate_journal(entries: Iterable[LedgerEntry]) -> bool:
    """A journal is balanced only when its debits and credits match exactly."""
    entries = list(entries)
    return bool(entries) and sum((entry.debit for entry in entries), Decimal(0)) == sum(
        (entry.credit for entry in entries), Decimal(0)
    )
