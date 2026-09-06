from __future__ import annotations

import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from packages.contracts import AuditEvent, Document, IngestionStatus


def _as_json(value: Any) -> Any:
    """Normalize SQLite TEXT JSON and PostgreSQL JSON/JSONB driver values."""
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return None
    return json.loads(value)


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
        if self.database_url.startswith("postgresql://"):
            self.database_url = self.database_url.replace(
                "postgresql://", "postgresql+psycopg://", 1
            )
        elif self.database_url.startswith("postgres://"):
            self.database_url = self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
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
                    """CREATE TABLE IF NOT EXISTS investigation_runs (
                        id TEXT PRIMARY KEY, reconciliation_run_id TEXT NOT NULL,
                        created_at TEXT NOT NULL, output_json TEXT NOT NULL,
                        telemetry_json TEXT NOT NULL
                    )"""
                )
            )
            connection.execute(
                text("""CREATE TABLE IF NOT EXISTS review_decisions (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL,
                    actor TEXT, reason TEXT, created_at TEXT NOT NULL, decided_at TEXT
                )""")
            )
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS reconciliation_runs (
                        id TEXT PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        status TEXT NOT NULL,
                        results_json TEXT NOT NULL,
                        exceptions_json TEXT NOT NULL
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
            row = (
                connection.execute(
                    text("SELECT * FROM ingestion_documents WHERE sha256 = :sha256"),
                    {"sha256": sha256},
                )
                .mappings()
                .first()
            )
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
            row = (
                connection.execute(
                    text(query),
                    {"now": now},
                )
                .mappings()
                .first()
            )
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
                        100 if status in {IngestionStatus.PARSED, IngestionStatus.FAILED} else 0
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
            row = (
                connection.execute(
                    text("SELECT * FROM ingestion_documents WHERE id = :id"),
                    {"id": str(document_id)},
                )
                .mappings()
                .first()
            )
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

    def create_reconciliation_run(
        self, *, results: list[dict[str, Any]], exceptions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        self._ensure_initialized()
        run_id = str(uuid4())
        created_at = datetime.now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO reconciliation_runs
                    (id, created_at, status, results_json, exceptions_json)
                    VALUES (:id, :created_at, 'COMPLETED', :results, :exceptions)"""
                ),
                {
                    "id": run_id,
                    "created_at": created_at,
                    "results": json.dumps(results),
                    "exceptions": json.dumps(exceptions),
                },
            )
        return self.get_reconciliation_run(run_id)  # type: ignore[return-value]

    def get_reconciliation_run(self, run_id: str) -> dict[str, Any] | None:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM reconciliation_runs WHERE id = :id"), {"id": run_id}
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "created_at": str(row["created_at"]),
            "status": row["status"],
            "results": _as_json(row["results_json"]),
            "exceptions": _as_json(row["exceptions_json"]),
        }

    def list_reconciliation_runs(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text("SELECT * FROM reconciliation_runs ORDER BY created_at DESC")
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": str(row["id"]),
                "created_at": str(row["created_at"]),
                "status": row["status"],
                "result_count": len(_as_json(row["results_json"])),
                "exception_count": len(_as_json(row["exceptions_json"])),
            }
            for row in rows
        ]

    def queue_review(self, run_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        review_id = str(uuid4())
        created_at = datetime.now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO review_decisions (id, run_id, status, created_at)
                    VALUES (:id, :run_id, 'PENDING', :created_at)
                    """
                ),
                {"id": review_id, "run_id": run_id, "created_at": created_at},
            )
        return self.get_review(review_id)  # type: ignore[return-value]

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM review_decisions WHERE id = :id"),
                    {"id": review_id},
                )
                .mappings()
                .first()
            )
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "run_id": str(row["run_id"]),
            "status": row["status"],
            "actor": row["actor"],
            "reason": row["reason"],
            "created_at": str(row["created_at"]),
            "decided_at": None if row["decided_at"] is None else str(row["decided_at"]),
        }

    def decide_review(
        self, review_id: str, *, decision: str, actor: str, reason: str
    ) -> dict[str, Any] | None:
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE review_decisions
                    SET status = :status, actor = :actor, reason = :reason,
                        decided_at = :decided_at
                    WHERE id = :id AND status = 'PENDING'
                    """
                ),
                {
                    "status": decision,
                    "actor": actor,
                    "reason": reason,
                    "decided_at": datetime.now().isoformat(),
                    "id": review_id,
                },
            )
        return self.get_review(review_id) if result.rowcount == 1 else None

    def list_pending_reviews(self) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                    SELECT * FROM review_decisions
                    WHERE status = 'PENDING'
                    ORDER BY created_at DESC
                    """
                    )
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": str(row["id"]),
                "run_id": str(row["run_id"]),
                "status": row["status"],
                "actor": row["actor"],
                "reason": row["reason"],
                "created_at": str(row["created_at"]),
                "decided_at": None if row["decided_at"] is None else str(row["decided_at"]),
            }
            for row in rows
        ]

    def save_investigation(
        self, run_id: str, *, output: dict[str, Any], telemetry: dict[str, Any]
    ) -> dict[str, Any]:
        investigation_id = str(uuid4())
        created_at = datetime.now().isoformat()
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO investigation_runs
                    (id, reconciliation_run_id, created_at, output_json, telemetry_json)
                    VALUES (:id, :run_id, :created_at, :output, :telemetry)"""
                ),
                {
                    "id": investigation_id,
                    "run_id": run_id,
                    "created_at": created_at,
                    "output": json.dumps(output),
                    "telemetry": json.dumps(telemetry),
                },
            )
        return {
            "id": investigation_id,
            "reconciliation_run_id": run_id,
            "created_at": created_at,
            "output": output,
            "telemetry": telemetry,
        }

    def list_investigations(self, run_id: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """SELECT * FROM investigation_runs
                    WHERE reconciliation_run_id = :run_id ORDER BY created_at DESC"""
                    ),
                    {"run_id": run_id},
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": row["id"],
                "reconciliation_run_id": row["reconciliation_run_id"],
                "created_at": row["created_at"],
                "output": _as_json(row["output_json"]),
                "telemetry": _as_json(row["telemetry_json"]),
            }
            for row in rows
        ]

    def list_all_investigations(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """SELECT * FROM investigation_runs
                        ORDER BY created_at DESC LIMIT :limit"""
                    ),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": row["id"],
                "reconciliation_run_id": row["reconciliation_run_id"],
                "created_at": row["created_at"],
                "output": _as_json(row["output_json"]),
                "telemetry": _as_json(row["telemetry_json"]),
            }
            for row in rows
        ]

    def list_audit_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                    SELECT * FROM audit_events
                    ORDER BY occurred_at DESC
                    LIMIT :limit
                    """
                    ),
                    {"limit": limit},
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "occurred_at": row["occurred_at"],
                "reason": row["reason"],
                "details": _as_json(row["details_json"]),
            }
            for row in rows
        ]

    def audit_events(self, document_id: UUID) -> list[dict[str, Any]]:
        self._ensure_initialized()
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    text("SELECT * FROM audit_events WHERE entity_id = :id ORDER BY occurred_at"),
                    {"id": str(document_id)},
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "actor": row["actor"],
                "entity_type": row["entity_type"],
                "entity_id": row["entity_id"],
                "occurred_at": row["occurred_at"],
                "reason": row["reason"],
                "details": _as_json(row["details_json"]),
            }
            for row in rows
        ]

    def dashboard_metrics(self) -> dict[str, int | str]:
        """Return ingestion-backed and reconciliation-backed dashboard metrics."""
        self._ensure_initialized()
        dialect = self.engine.dialect.name
        with self.engine.connect() as connection:
            if dialect == "postgresql":
                processed_row = (
                    connection.execute(
                        text(
                            """
                        SELECT COALESCE(
                            SUM(jsonb_array_length(records_json)), 0
                        ) AS processed
                        FROM ingestion_documents
                        WHERE status IN ('PARSED', 'CONFIRMED')
                        """
                        )
                    )
                    .mappings()
                    .one()
                )
            else:
                processed_row = (
                    connection.execute(
                        text(
                            """
                        SELECT COALESCE(SUM(json_array_length(records_json)), 0) AS processed
                        FROM ingestion_documents
                        WHERE status IN ('PARSED', 'CONFIRMED')
                        """
                        )
                    )
                    .mappings()
                    .one()
                )

            run_rows = (
                connection.execute(
                    text("SELECT results_json, exceptions_json FROM reconciliation_runs")
                )
                .mappings()
                .all()
            )
            pending_reviews = (
                connection.execute(
                    text("SELECT COUNT(*) AS count FROM review_decisions WHERE status = 'PENDING'")
                )
                .mappings()
                .one()["count"]
            )

        matched = 0
        exceptions = 0
        amount_at_risk = Decimal(0)
        for row in run_rows:
            results = _as_json(row["results_json"])
            run_exceptions = _as_json(row["exceptions_json"])
            matched += sum(1 for item in results if item.get("status") == "MATCHED")
            exceptions += len(run_exceptions)
            amount_at_risk += Decimal(len(run_exceptions))

        total = matched + exceptions
        reconciliation_rate = int((matched / total) * 100) if total else 0
        return {
            "transactions_processed": int(processed_row["processed"]),
            "reconciled_count": matched,
            "reconciliation_rate": reconciliation_rate,
            "exception_count": exceptions,
            "amount_at_risk": format(amount_at_risk, "f") if amount_at_risk else "0.00",
            "pending_reviews": int(pending_reviews),
            "automation_rate": reconciliation_rate,
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
            "column_mapping": _as_json(row["column_mapping_json"]),
            "object_key": row["object_key"],
            "records": _as_json(row["records_json"]),
            "preview": _as_json(row["preview_json"]),
            "errors": _as_json(row["errors_json"]),
        }
