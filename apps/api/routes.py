from __future__ import annotations

import hashlib
import json
import os
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from packages.contracts import AuditEvent, Document, IngestionStatus, Invoice

from .storage import DocumentStore

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))


def create_router(store: DocumentStore) -> APIRouter:
    router = APIRouter()

    def audit(document_id: UUID, event_type: str, details: dict[str, object]) -> None:
        store.add_audit(
            AuditEvent(
                event_type=event_type,
                actor="upload_api",
                entity_type="Document",
                entity_id=document_id,
                occurred_at=datetime.now(UTC),
                details=details,
            )
        )

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/dashboard/metrics")
    def dashboard_metrics() -> dict[str, int | str]:
        return store.dashboard_metrics()

    @router.get("/contracts/sample", response_model=Invoice)
    def sample_invoice() -> Invoice:
        return Invoice(
            invoice_number="INV-1001",
            amount=Decimal("1200.00"),
            currency="USD",
            record_date=date(2026, 1, 15),
            vendor_id="vendor-42",
            tax_amount=Decimal("100.00"),
        )

    @router.post("/documents/upload")
    async def upload_document(
        file: UploadFile = File(...),
        record_type: str = Form("invoice"),
        column_mapping: str | None = Form(None),
    ) -> dict[str, object]:
        filename = file.filename or "upload"
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix not in {"csv", "xlsx", "pdf"}:
            raise HTTPException(
                status_code=400,
                detail="Only CSV, XLSX, and PDF uploads are supported",
            )

        mapping = _parse_mapping(column_mapping)
        content = await file.read()
        _validate_upload(content, suffix)
        sha256 = hashlib.sha256(content).hexdigest()
        existing = store.find_by_hash(sha256)
        if existing:
            return _response(existing, duplicate=True)

        document = Document(
            id=uuid4(),
            filename=filename,
            media_type=file.content_type or "application/octet-stream",
            sha256=sha256,
            uploaded_at=datetime.now(UTC),
            source="upload",
        )
        object_key = f"documents/{document.id}/{filename}"
        store.objects.put(object_key, content, content_type=document.media_type)
        store.create(
            document=document,
            record_type=record_type,
            column_mapping=mapping,
            status=IngestionStatus.UPLOADED,
            object_key=object_key,
        )
        audit(document.id, "UPLOAD_RECEIVED", {"sha256": sha256, "filename": filename})
        store.enqueue_job(document.id)
        return _response(store.get(document.id))

    @router.get("/documents/{document_id}")
    def get_document(document_id: UUID) -> dict[str, object]:
        stored = _get_or_404(store, document_id)
        return _response(stored, include_records=False)

    @router.get("/documents/{document_id}/preview")
    def preview_document(document_id: UUID) -> dict[str, object]:
        stored = _get_or_404(store, document_id)
        return {
            "document_id": str(document_id),
            "rows": stored["preview"],
            "records": stored["records"],
            "errors": stored["errors"],
        }

    @router.get("/documents/{document_id}/errors")
    def document_errors(document_id: UUID) -> dict[str, object]:
        stored = _get_or_404(store, document_id)
        return {"document_id": str(document_id), "errors": stored["errors"]}

    @router.get("/documents/{document_id}/audit")
    def document_audit(document_id: UUID) -> dict[str, object]:
        _get_or_404(store, document_id)
        return {"document_id": str(document_id), "events": store.audit_events(document_id)}

    @router.post("/documents/{document_id}/confirm")
    def confirm_document(document_id: UUID) -> dict[str, object]:
        stored = _get_or_404(store, document_id)
        if stored["errors"]:
            raise HTTPException(
                status_code=409,
                detail="Cannot confirm a document with parse errors",
            )
        if not store.confirm(document_id):
            raise HTTPException(status_code=409, detail="Document is not awaiting confirmation")
        audit(document_id, "IMPORT_CONFIRMED", {"record_count": len(stored["records"])})
        return _response(store.get(document_id), include_records=False)

    @router.post("/documents/{document_id}/retry")
    def retry_document(document_id: UUID) -> dict[str, object]:
        stored = _get_or_404(store, document_id)
        if stored["status"] not in {IngestionStatus.FAILED.value, IngestionStatus.UPLOADED.value}:
            raise HTTPException(status_code=409, detail="Document is not retryable")
        store.enqueue_job(document_id)
        store.update_progress(
            document_id,
            status=IngestionStatus.UPLOADED,
            progress=0,
            message="Retry queued",
        )
        audit(document_id, "INGESTION_RETRY_REQUESTED", {})
        return _response(store.get(document_id), include_records=False)

    return router


def _parse_mapping(column_mapping: str | None) -> dict[str, str] | None:
    if not column_mapping:
        return None
    try:
        mapping = json.loads(column_mapping)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="column_mapping must be valid JSON") from exc
    if not isinstance(mapping, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()
    ):
        raise HTTPException(status_code=400, detail="column_mapping must be an object of strings")
    return mapping


def _validate_upload(content: bytes, suffix: str) -> None:
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the configured size limit")
    if suffix == "csv":
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc
    elif suffix == "xlsx":
        if not content.startswith(b"PK"):
            raise HTTPException(status_code=400, detail="XLSX signature is invalid")
        if not zipfile.is_zipfile(BytesIO(content)):
            raise HTTPException(status_code=400, detail="XLSX archive is invalid")
    elif not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="PDF signature is invalid")


def _get_or_404(store: DocumentStore, document_id: UUID) -> dict[str, object]:
    stored = store.get(document_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return stored


def _response(
    stored: dict[str, object] | None,
    *,
    duplicate: bool = False,
    include_records: bool = True,
) -> dict[str, object]:
    if stored is None:
        raise HTTPException(status_code=404, detail="Document not found")
    response: dict[str, object] = {
        "document": stored["document"].model_dump(mode="json"),
        "status": stored["status"],
        "progress": stored["progress"],
        "progress_message": stored["progress_message"],
        "record_count": len(stored["records"]),
        "error_count": len(stored["errors"]),
    }
    if include_records:
        response["records"] = stored["records"]
    if duplicate:
        response["duplicate"] = True
    return response

