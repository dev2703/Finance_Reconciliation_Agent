from __future__ import annotations

import os
import time
from datetime import UTC, date, datetime
from uuid import UUID

from apps.api.storage import DocumentStore
from packages.contracts import AuditEvent, IngestionStatus, ParseError
from services.ingestion.pdf import extract_pdf, _extract_tables_pdfplumber
from services.ingestion.tabular import parse_csv_result, parse_xlsx_result, preview_rows

MAX_ROWS = int(os.getenv("MAX_INGESTION_ROWS", "10000"))
MAX_SHEETS = int(os.getenv("MAX_INGESTION_SHEETS", "20"))
MAX_ATTEMPTS = int(os.getenv("MAX_INGESTION_ATTEMPTS", "3"))
PDF_CONFIDENCE_THRESHOLD = float(os.getenv("PDF_CONFIDENCE_THRESHOLD", "0.3"))


def run_once(store: DocumentStore) -> bool:
    job = store.claim_job()
    if job is None:
        return False
    document_id = UUID(job["document_id"])
    try:
        process_document(store, document_id)
        store.complete_job(job["id"])
    except Exception as exc:
        error = str(exc)
        if job["attempts"] >= MAX_ATTEMPTS:
            store.fail_job(job["id"], error=error)
            store.update_progress(
                document_id,
                status=IngestionStatus.FAILED,
                progress=100,
                message="Ingestion failed after retries",
            )
            _audit(store, document_id, "INGESTION_RETRY_EXHAUSTED", {"error": error})
        else:
            delay = 2 ** (job["attempts"] - 1)
            store.retry_job(job["id"], error=error, delay_seconds=delay)
            store.update_progress(
                document_id,
                status=IngestionStatus.UPLOADED,
                progress=0,
                message=f"Retry scheduled in {delay}s",
            )
            _audit(
                store,
                document_id,
                "INGESTION_RETRY_SCHEDULED",
                {"error": error, "attempt": job["attempts"], "delay_seconds": delay},
            )
    return True


def process_document(store: DocumentStore, document_id: UUID) -> None:
    stored = store.get(document_id)
    if stored is None:
        raise ValueError("Document not found")
    document = stored["document"]
    suffix = document.filename.rsplit(".", 1)[-1].lower()
    store.update_progress(
        document_id,
        status=IngestionStatus.INGESTING,
        progress=10,
        message="Reading uploaded object",
    )
    _audit(store, document_id, "INGESTION_STARTED", {"record_type": stored["record_type"]})
    content = store.objects.get(stored["object_key"])
    store.update_progress(
        document_id,
        status=IngestionStatus.INGESTING,
        progress=45,
        message="Parsing tabular records",
    )
    if suffix == "pdf":
        pdf_result = extract_pdf(content, source_name=document.filename)
        store.update_progress(
            document_id,
            status=IngestionStatus.INGESTING,
            progress=70,
            message="Extracting tables and converting to records",
        )
        # Process tables to extract financial records
        records = _extract_records_from_pdf(
            pdf_result, 
            record_type=stored.get("record_type", "BankTransaction"),
            document_id=document_id
        )
        records = [
            record.model_copy(update={"source_document_id": document_id})
            for record in records.get("records", [])
        ]
        errors = [error.__dict__ for error in records.get("errors", [])]
        status = IngestionStatus.PARSED  # For now, assume parsing succeeds even with low confidence
        store.update_result(
            document_id,
            status=status,
            records=[record.model_dump(mode="json") for record in records],
            preview=pdf_result,
            errors=errors,
        )
        _audit(
            store,
            document_id,
            "INGESTION_COMPLETED",
            {
                "page_count": len(pdf_result), 
                "record_count": len(records), 
                "error_count": len(errors),
                "extraction_methods": list(set(p.get("extraction_method") for p in pdf_result))
            },
        )
        return
    if suffix == "csv":
        result = parse_csv_result(
            content,
            record_type=stored["record_type"],
            source_name=document.filename,
            column_mapping=stored["column_mapping"],
            max_rows=MAX_ROWS,
        )
    else:
        result = parse_xlsx_result(
            content,
            record_type=stored["record_type"],
            source_name=document.filename,
            column_mapping=stored["column_mapping"],
            max_sheets=MAX_SHEETS,
            max_rows=MAX_ROWS,
        )
    records = [
        record.model_copy(update={"source_document_id": document_id})
        for record in result.records
    ]
    errors = [error.__dict__ for error in result.errors]
    status = IngestionStatus.FAILED if errors else IngestionStatus.PARSED
    store.update_result(
        document_id,
        status=status,
        records=[record.model_dump(mode="json") for record in records],
        preview=_json_safe(preview_rows(content, file_type=suffix)),
        errors=errors,
    )
    _audit(
        store,
        document_id,
        "INGESTION_COMPLETED" if not errors else "INGESTION_FAILED",
        {"record_count": len(records), "error_count": len(errors)},
    )


def run_worker(store: DocumentStore | None = None) -> None:
    worker_store = store or DocumentStore()
    while True:
        if not run_once(worker_store):
            time.sleep(1)


def _audit(
    store: DocumentStore,
    document_id: UUID,
    event_type: str,
    details: dict[str, object],
) -> None:
    store.add_audit(
        AuditEvent(
            event_type=event_type,
            actor="ingestion_worker",
            entity_type="Document",
            entity_id=document_id,
            occurred_at=datetime.now(UTC),
            details=details,
        )
    )


def _json_safe(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _extract_records_from_pdf(
    pages: list[dict],
    record_type: str,
    document_id: UUID,
) -> dict[str, list]:
    """Extract financial records from PDF pages and tables.
    
    Returns dict with 'records' and 'errors' lists.
    For now, this is a pass-through that returns empty records.
    Full table-to-record conversion is in phase 2.5 (extraction agent).
    """
    records = []
    errors = []
    
    # Future: Process tables to extract financial records
    # For now, just mark that PDF was parsed successfully
    for page in pages:
        if page.get("confidence", 0) < PDF_CONFIDENCE_THRESHOLD:
            # Low confidence page - could mark for human review
            pass
        
        # Tables exist on this page
        if page.get("tables"):
            # Table extraction infrastructure is in place
            # Actual record extraction will be done by extraction agent
            pass
    
    return {"records": records, "errors": errors}


if __name__ == "__main__":
    run_worker()
