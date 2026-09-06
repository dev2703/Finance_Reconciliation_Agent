from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from packages.contracts import AuditEvent, Document, IngestionStatus


class ObjectStore(Protocol):
    def put(self, key: str, content: bytes, *, content_type: str) -> None: ...

    def get(self, key: str) -> bytes: ...


class FileObjectStore:
    """Filesystem-backed storage for the local MVP."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or os.getenv("OBJECT_STORAGE_PATH", ".data/objects"))
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes, *, content_type: str) -> None:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


def default_object_store() -> ObjectStore:
    return FileObjectStore()


class DocumentStore:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        object_store: ObjectStore | None = None,
    ) -> None:
        self.database_url = database_url or os.getenv(
            "DATABASE_URL",
            "sqlite:///./.data/finance_reconciliation.sqlite3",
        )
        self.engine = create_engine(self.database_url, future=True, pool_pre_ping=True)
        self.objects = object_store or default_object_store()
        self._initialized = False
        try:
            self._initialize()
        except OperationalError:
            pass

    def _initialize(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_documents (
                        id TEXT PRIMARY KEY,
                        filename TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        sha256 TEXT NOT NULL UNIQUE,
                        uploaded_at TEXT NOT NULL,
                        source TEXT NOT NULL,
                        status TEXT NOT NULL,
                        progress INTEGER NOT NULL DEFAULT 0,
                        progress_message TEXT NOT NULL DEFAULT '',
                        record_type TEXT NOT NULL,
                        column_mapping_json TEXT NOT NULL DEFAULT '{}',
                        object_key TEXT NOT NULL,
                        records_json TEXT NOT NULL DEFAULT '[]',
                        preview_json TEXT NOT NULL DEFAULT '[]',
                        errors_json TEXT NOT NULL DEFAULT '[]'
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS ingestion_jobs (
                        id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL UNIQUE,
                        status TEXT NOT NULL,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        available_at TEXT NOT NULL,
                        locked_at TEXT,
                        last_error TEXT
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        actor TEXT NOT NULL,
                        entity_type TEXT NOT NULL,
                        entity_id TEXT NOT NULL,
                        occurred_at TEXT NOT NULL,
                        reason TEXT,
                        details_json TEXT NOT NULL DEFAULT '{}'
                    )
                    """
                )
            )
        self._initialized = True

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._initialize()

    def find_by_hash(self, sha256: str) -> dict[str, Any] | None:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM ingestion_documents WHERE sha256 = :sha256"),
                {"sha256": sha256},
            ).mappings().first()
        return self._deserialize(row) if row else None

    def create(
        self,
        *,
        document: Document,
        record_type: str,
        column_mapping: dict[str, str] | None,
        status: IngestionStatus,
        object_key: str,
    ) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ingestion_documents
                        (id, filename, media_type, sha256, uploaded_at, source, status,
                         progress, progress_message, record_type, column_mapping_json, object_key)
                    VALUES (:id, :filename, :media_type, :sha256, :uploaded_at, :source,
                            :status, :progress, :progress_message, :record_type,
                            :column_mapping, :object_key)
                    """
                ),
                {
                    "id": str(document.id),
                    "filename": document.filename,
                    "media_type": document.media_type,
                    "sha256": document.sha256,
                    "uploaded_at": document.uploaded_at.isoformat(),
                    "source": document.source,
                    "status": status.value,
                    "progress": 0,
                    "progress_message": "Upload received",
                    "record_type": record_type,
                    "column_mapping": json.dumps(column_mapping or {}),
                    "object_key": object_key,
                },
            )

    def update_progress(
        self,
        document_id: UUID,
        *,
        status: IngestionStatus,
        progress: int,
        message: str,
    ) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE ingestion_documents
                    SET status = :status, progress = :progress, progress_message = :message
                    WHERE id = :id
                    """
                ),
                {
                    "status": status.value,
                    "progress": progress,
                    "message": message,
                    "id": str(document_id),
                },
            )

    def enqueue_job(self, document_id: UUID) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO ingestion_jobs
                    (id, document_id, status, attempts, available_at)
                    VALUES (:id, :document_id, 'QUEUED', 0, :available_at)
                    ON CONFLICT (document_id) DO UPDATE SET
                        status = 'QUEUED', attempts = 0, available_at = :available_at,
                        locked_at = NULL, last_error = NULL
                    """
                ),
                {
                    "id": str(uuid4()),
                    "document_id": str(document_id),
                    "available_at": datetime.now().isoformat(),
                },
            )

    def claim_job(self) -> dict[str, Any] | None:
        self._ensure_initialized()
        now = datetime.now().isoformat()
        with self.engine.begin() as connection:
            query = (
                "SELECT * FROM ingestion_jobs "
                "WHERE status IN ('QUEUED', 'RETRY') AND available_at <= :now "
                "ORDER BY available_at LIMIT 1"
            )
            if self.engine.dialect.name == "postgresql":
                query += " FOR UPDATE SKIP LOCKED"
            row = connection.execute(
                text(query),
                {"now": now},
            ).mappings().first()
            if row is None:
                return None
            connection.execute(
                text(
                    "UPDATE ingestion_jobs SET status = 'RUNNING', locked_at = :now, "
                    "attempts = attempts + 1 WHERE id = :id"
                ),
                {"now": now, "id": row["id"]},
            )
            return {**dict(row), "attempts": row["attempts"] + 1}

    def complete_job(self, job_id: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text("UPDATE ingestion_jobs SET status = 'COMPLETED' WHERE id = :id"),
                {"id": job_id},
            )

    def retry_job(self, job_id: str, *, error: str, delay_seconds: int) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ingestion_jobs SET status = 'RETRY', last_error = :error, "
                    "available_at = :available_at WHERE id = :id"
                ),
                {
                    "error": error,
                    "available_at": datetime.fromtimestamp(
                        datetime.now().timestamp() + delay_seconds
                    ).isoformat(),
                    "id": job_id,
                },
            )

    def fail_job(self, job_id: str, *, error: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE ingestion_jobs SET status = 'FAILED', last_error = :error "
                    "WHERE id = :id"
                ),
                {"error": error, "id": job_id},
            )

    def update_result(
        self,
        document_id: UUID,
        *,
        status: IngestionStatus,
        records: list[dict[str, Any]],
        preview: list[Any],
        errors: list[dict[str, Any]],
    ) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE ingestion_documents
                    SET status = :status, progress = :progress, progress_message = :message,
                        records_json = :records, preview_json = :preview, errors_json = :errors
                    WHERE id = :id
                    """
                ),
                {
                    "status": status.value,
                    "progress": (
                        100
                        if status in {IngestionStatus.PARSED, IngestionStatus.FAILED}
                        else 0
                    ),
                    "message": (
                        "Ready for confirmation"
                        if status == IngestionStatus.PARSED
                        else "Ingestion failed"
                    ),
                    "records": json.dumps(records),
                    "preview": json.dumps(preview),
                    "errors": json.dumps(errors),
                    "id": str(document_id),
                },
            )

    def get(self, document_id: UUID) -> dict[str, Any] | None:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM ingestion_documents WHERE id = :id"),
                {"id": str(document_id)},
            ).mappings().first()
        return self._deserialize(row) if row else None

    def confirm(self, document_id: UUID) -> bool:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    "UPDATE ingestion_documents "
                    "SET status = :confirmed, progress_message = :message "
                    "WHERE id = :id AND status = :parsed"
                ),
                {
                    "confirmed": IngestionStatus.CONFIRMED.value,
                    "message": "Import confirmed",
                    "id": str(document_id),
                    "parsed": IngestionStatus.PARSED.value,
                },
            )
        return result.rowcount == 1

    def add_audit(self, event: AuditEvent) -> None:
        self._ensure_initialized()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO audit_events
                    (id, event_type, actor, entity_type, entity_id, occurred_at,
                     reason, details_json)
                    VALUES (:id, :event_type, :actor, :entity_type, :entity_id, :occurred_at,
                            :reason, :details)
                    """
                ),
                {
                    "id": str(event.id),
                    "event_type": event.event_type,
                    "actor": event.actor,
                    "entity_type": event.entity_type,
                    "entity_id": str(event.entity_id),
                    "occurred_at": event.occurred_at.isoformat(),
                    "reason": event.reason,
                    "details": json.dumps(event.details),
                },
            )

    def audit_events(self, document_id: UUID) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT * FROM audit_events WHERE entity_id = :id ORDER BY occurred_at"),
                {"id": str(document_id)},
            ).mappings().all()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "occurred_at": row["occurred_at"],
                "reason": row["reason"],
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

    def dashboard_metrics(self) -> dict[str, int | str]:
        """Return ingestion-backed metrics available before reconciliation persistence exists."""
        self._ensure_initialized()
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT COALESCE(SUM(json_array_length(records_json)), 0) AS processed "
                    "FROM ingestion_documents WHERE status IN ('PARSED', 'CONFIRMED')"
                )
            ).mappings().one()
        # SQLite's JSON aggregate is used by the local MVP. PostgreSQL dashboard
        # metrics will be sourced from reconciliation runs when those are persisted.
        return {
            "transactions_processed": int(row["processed"]),
            "reconciled_count": 0,
            "reconciliation_rate": 0,
            "exception_count": 0,
            "amount_at_risk": "0.00",
            "pending_reviews": 0,
            "automation_rate": 0,
        }

    @staticmethod
    def _deserialize(row: Any) -> dict[str, Any]:
        return {
            "document": Document(
                id=UUID(row["id"]),
                filename=row["filename"],
                media_type=row["media_type"],
                sha256=row["sha256"],
                uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
                source=row["source"],
            ),
            "status": row["status"],
            "progress": row["progress"],
            "progress_message": row["progress_message"],
            "record_type": row["record_type"],
            "column_mapping": json.loads(row["column_mapping_json"]),
            "object_key": row["object_key"],
            "records": json.loads(row["records_json"]),
            "preview": json.loads(row["preview_json"]),
            "errors": json.loads(row["errors_json"]),
        }
