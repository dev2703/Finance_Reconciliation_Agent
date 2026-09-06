from __future__ import annotations

import hashlib
import json
import logging
import os
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import Field

from packages.contracts import AuditEvent, Document, FinancialRecord, IngestionStatus, Invoice
from packages.contracts.models import ContractModel
from services.agents.controller import investigate_unresolved_case
from services.agents.tensormux import TensorMuxError
from services.ml.contracts import Candidate
from services.ml.model import rank_candidates
from services.reconciliation.deterministic import reconcile_records
from services.reconciliation.deterministic.engine import audit_events_for_results

from .storage import DocumentStore

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))


class ReconciliationRequest(ContractModel):
    sources: list[FinancialRecord] = Field(min_length=1, max_length=10_000)
    targets: list[FinancialRecord] = Field(min_length=1, max_length=10_000)
    date_window_days: int = Field(default=3, ge=0, le=365)
    max_allocation_group_size: int = Field(default=4, ge=2, le=10)


class MLReviewRequest(ContractModel):
    """A complete candidate batch for conflict-aware, review-only ranking."""

    candidates: list[Candidate] = Field(min_length=1, max_length=1_000)


class ReviewDecisionRequest(ContractModel):
    decision: str = Field(pattern="^(AUTO_APPROVE|REJECT|ESCALATE)$")
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def create_router(store: DocumentStore, ml_model_directory: Path | None = None) -> APIRouter:
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

    @router.post("/reconciliation/match")
    def reconcile(request: ReconciliationRequest) -> dict[str, object]:
        results = reconcile_records(
            request.sources,
            request.targets,
            date_window_days=request.date_window_days,
            max_allocation_group_size=request.max_allocation_group_size,
        )
        events = audit_events_for_results(results, actor="reconciliation_api")
        return {
            "results": [result.model_dump(mode="json") for result in results],
            "audit_events": [event.model_dump(mode="json") for event in events],
        }

    @router.post("/reconciliation/runs")
    def create_reconciliation_run(request: ReconciliationRequest) -> dict[str, object]:
        results = reconcile_records(
            request.sources,
            request.targets,
            date_window_days=request.date_window_days,
            max_allocation_group_size=request.max_allocation_group_size,
        )
        serialized = [result.model_dump(mode="json") for result in results]
        exceptions = [
            result for result in serialized if result["status"] in {"EXCEPTION", "UNMATCHED"}
        ]
        run = store.create_reconciliation_run(results=serialized, exceptions=exceptions)
        store.add_audit(
            AuditEvent(
                event_type="RECONCILIATION_RUN_COMPLETED",
                actor="reconciliation_api",
                entity_type="ReconciliationRun",
                entity_id=UUID(run["id"]),
                occurred_at=datetime.now(UTC),
                details={"result_count": len(serialized), "exception_count": len(exceptions)},
            )
        )
        return run

    @router.get("/reconciliation/runs")
    def list_reconciliation_runs() -> dict[str, object]:
        return {"runs": store.list_reconciliation_runs()}

    @router.get("/reconciliation/runs/{run_id}")
    def get_reconciliation_run(run_id: UUID) -> dict[str, object]:
        run = store.get_reconciliation_run(str(run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="Reconciliation run not found")
        return run

    @router.get("/reconciliation/runs/{run_id}/exceptions")
    def list_run_exceptions(run_id: UUID) -> dict[str, object]:
        run = store.get_reconciliation_run(str(run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="Reconciliation run not found")
        return {"run_id": str(run_id), "exceptions": run["exceptions"]}

    @router.post("/reconciliation/runs/{run_id}/investigate")
    def investigate_run(run_id: UUID) -> dict[str, object]:
        run = store.get_reconciliation_run(str(run_id))
        if run is None:
            raise HTTPException(status_code=404, detail="Reconciliation run not found")
        if not run["exceptions"]:
            raise HTTPException(status_code=409, detail="Run has no unresolved exceptions")
        try:
            result = investigate_unresolved_case(
                case_id=str(run_id),
                evidence=[{"match_result": item} for item in run["exceptions"][:30]],
            )
        except (TensorMuxError, ValueError) as exc:
            # Keep gateway details out of the browser response, but retain the
            # safe exception summary in service logs for deployment diagnosis.
            logger.warning("TensorMux investigation unavailable: %s", exc)
            raise HTTPException(
                status_code=503, detail="TensorMux investigation is unavailable"
            ) from exc
        investigation = store.save_investigation(str(run_id), **result)
        store.add_audit(
            AuditEvent(
                event_type="INVESTIGATION_COMPLETED",
                actor="glm-4.7-flash",
                entity_type="ReconciliationRun",
                entity_id=run_id,
                occurred_at=datetime.now(UTC),
                details={
                    "investigation_id": investigation["id"],
                    "model": result["telemetry"]["model"],
                    "prompt_tokens": result["telemetry"]["prompt_tokens"],
                    "completion_tokens": result["telemetry"]["completion_tokens"],
                },
            )
        )
        return investigation

    @router.get("/reconciliation/runs/{run_id}/investigations")
    def list_run_investigations(run_id: UUID) -> dict[str, object]:
        if store.get_reconciliation_run(str(run_id)) is None:
            raise HTTPException(status_code=404, detail="Reconciliation run not found")
        return {
            "run_id": str(run_id),
            "investigations": store.list_investigations(str(run_id)),
        }

    @router.post("/reconciliation/runs/{run_id}/reviews")
    def queue_review(run_id: UUID) -> dict[str, object]:
        if store.get_reconciliation_run(str(run_id)) is None:
            raise HTTPException(status_code=404, detail="Reconciliation run not found")
        review = store.queue_review(str(run_id))
        return review

    @router.post("/reviews/{review_id}/decision")
    def decide_review(review_id: UUID, request: ReviewDecisionRequest) -> dict[str, object]:
        review = store.decide_review(
            str(review_id),
            decision=request.decision,
            actor=request.actor,
            reason=request.reason,
        )
        if review is None:
            raise HTTPException(status_code=409, detail="Review is missing or already decided")
        store.add_audit(
            AuditEvent(
                event_type="REVIEW_DECIDED",
                actor=request.actor,
                entity_type="Review",
                entity_id=review_id,
                occurred_at=datetime.now(UTC),
                reason=request.reason,
                details={"decision": request.decision, "run_id": review.get("run_id")},
            )
        )
        return review

    @router.get("/reviews/pending")
    def pending_reviews() -> dict[str, object]:
        return {"reviews": store.list_pending_reviews()}

    @router.get("/reports/operational")
    def operational_reports() -> dict[str, object]:
        runs = store.list_reconciliation_runs()
        items = []
        events = store.list_audit_events(limit=500)
        for summary in runs:
            run = store.get_reconciliation_run(summary["id"])
            if run is None:
                continue
            for result in run["results"]:
                source_ids = result.get("source_record_ids") or []
                items.append(
                    {
                        "id": source_ids[0] if source_ids else None,
                        "status": result["status"],
                        "confidence": result.get("confidence", "0"),
                        "reason_codes": result.get("reason_codes", []),
                    }
                )
        matched = sum(1 for item in items if item["status"] == "MATCHED")
        exceptions = [item for item in items if item["status"] in {"EXCEPTION", "UNMATCHED"}]
        total = len(items)
        rate = format(Decimal(matched) / Decimal(total), "f") if total else "0"
        automation = sum(
            1 for event in events if event["event_type"] in {"AUTO_APPROVED", "AUTO_RECONCILED"}
        )
        automation_rate = format(Decimal(automation) / Decimal(total), "f") if total else "0"
        return {
            "reconciliation": {
                "item_count": total,
                "matched_count": matched,
                "reconciliation_rate": rate,
                "run_count": len(runs),
            },
            "exceptions": {
                "exception_count": len(exceptions),
                "item_ids": [str(item["id"]) for item in exceptions if item["id"]],
            },
            "audit": {
                "event_count": len(events),
                "event_types": [event["event_type"] for event in events],
            },
            "automation": {
                "automated_count": automation,
                "automation_rate": automation_rate,
                "pending_reviews": len(store.list_pending_reviews()),
            },
        }

    @router.get("/audit/events")
    def audit_event_feed(limit: int = 100) -> dict[str, object]:
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
        return {"events": store.list_audit_events(limit=limit)}

    @router.get("/agent-traces")
    def agent_trace_feed(limit: int = 100) -> dict[str, object]:
        if limit < 1 or limit > 500:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 500")
        return {"traces": store.list_all_investigations(limit=limit)}

    @router.post("/demo/seed-and-run")
    def seed_and_run_demo() -> dict[str, object]:
        """Seed the Phase 19 demo pack and persist one reconciliation run."""
        from evaluation.demo import build_demo_cases
        from services.demo import financial_pairs_from_demo_cases, run_reconciliation

        cases = list(build_demo_cases())
        sources, targets = financial_pairs_from_demo_cases(cases)
        outcome = run_reconciliation(sources, targets)
        run = store.create_reconciliation_run(
            results=outcome["results"],
            exceptions=outcome["exceptions"],
        )
        review = None
        if outcome["exceptions"]:
            review = store.queue_review(run["id"])
        store.add_audit(
            AuditEvent(
                event_type="DEMO_RECONCILIATION_COMPLETED",
                actor="demo_orchestrator",
                entity_type="ReconciliationRun",
                entity_id=UUID(run["id"]),
                occurred_at=datetime.now(UTC),
                details={
                    "case_count": len(cases),
                    "matched_count": outcome["matched_count"],
                    "exception_count": outcome["exception_count"],
                },
            )
        )
        return {
            "run": run,
            "review": review,
            "case_count": len(cases),
            "matched_count": outcome["matched_count"],
            "exception_count": outcome["exception_count"],
        }

    @router.post("/demo/ml-review")
    def ml_review(request: MLReviewRequest) -> dict[str, object]:
        """Return synthetic-demo ML suggestions without mutating any record."""
        if ml_model_directory is None:
            raise HTTPException(
                status_code=503,
                detail="ML review is not configured; set ML_MODEL_DIRECTORY",
            )
        try:
            suggestions = rank_candidates(ml_model_directory, request.candidates)
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=503,
                detail="ML review artifact is unavailable or incompatible",
            ) from exc
        # Defense in depth: this endpoint must remain incapable of automation.
        if any(item["automatic_action_eligible"] for item in suggestions):
            raise HTTPException(status_code=503, detail="ML review policy violation")
        return {"suggestions": suggestions, "mode": "REVIEW_ONLY"}

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
