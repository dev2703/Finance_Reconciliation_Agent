"""FinBalance offline loader for document/accounting ingestion benchmarks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from services.ml.datasets.contracts import DatasetFormatError


def _fail(path: Path, message: str, line: int | None = None) -> DatasetFormatError:
    location = f"{path}:{line}" if line is not None else str(path)
    return DatasetFormatError(f"{location}: {message}")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_text(value: Any, name: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, f"{name} must be a non-empty string")
    return value.strip()


def _decimal(value: Any, name: str, path: Path) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        raise _fail(path, f"{name} must be an exact decimal string or integer")
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _fail(path, f"{name} is not a valid decimal amount") from exc
    if not parsed.is_finite():
        raise _fail(path, f"{name} must be finite")
    return parsed


@dataclass(frozen=True)
class FinBalanceCase:
    """One FinBalance document/accounting evaluation case."""

    case_id: str
    industry: str
    complexity: str
    document_path: Path
    ocr_text: str
    expected_journal_entries: tuple[Mapping[str, Any], ...]
    contradiction_labels: tuple[str, ...]
    expected_fields: Mapping[str, Any]
    amounts: tuple[Decimal, ...]
    provenance_sha256: str


def load_finbalance(root: str | Path) -> tuple[FinBalanceCase, ...]:
    """Load a FinBalance-style offline pack.

    Expected layout::

        root/
          manifest.json
          cases/<case_id>/case.json
          cases/<case_id>/document.txt   # OCR/native text stand-in

    ``manifest.json`` must list ``case_ids`` and optional ``pack_id``.
    Each ``case.json`` requires ``case_id``, ``industry``, ``complexity``,
    ``expected_journal_entries``, ``contradiction_labels``, and ``expected_fields``.
    """
    root = Path(root)
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail(manifest_path, f"invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict):
        raise _fail(manifest_path, "top-level value must be an object")
    case_ids = manifest.get("case_ids")
    if not isinstance(case_ids, list) or not case_ids:
        raise _fail(manifest_path, "case_ids must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in case_ids):
        raise _fail(manifest_path, "case_ids must contain non-empty strings")
    if len(set(case_ids)) != len(case_ids):
        raise _fail(manifest_path, "case_ids must be unique")

    cases: list[FinBalanceCase] = []
    for case_id in case_ids:
        case_dir = root / "cases" / case_id
        case_path = case_dir / "case.json"
        document_path = case_dir / "document.txt"
        try:
            payload = json.loads(case_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise _fail(case_path, f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise _fail(case_path, "top-level value must be an object")
        payload_id = _required_text(payload.get("case_id"), "case_id", case_path)
        if payload_id != case_id:
            raise _fail(case_path, "case_id does not match directory/manifest")
        industry = _required_text(payload.get("industry"), "industry", case_path)
        complexity = _required_text(payload.get("complexity"), "complexity", case_path)
        journals = payload.get("expected_journal_entries")
        contradictions = payload.get("contradiction_labels")
        expected_fields = payload.get("expected_fields")
        if not isinstance(journals, list) or not journals:
            raise _fail(case_path, "expected_journal_entries must be a non-empty list")
        if any(not isinstance(item, dict) for item in journals):
            raise _fail(case_path, "journal entries must be objects")
        if not isinstance(contradictions, list) or any(
            not isinstance(item, str) or not item.strip() for item in contradictions
        ):
            raise _fail(case_path, "contradiction_labels must be a list of non-empty strings")
        if not isinstance(expected_fields, dict):
            raise _fail(case_path, "expected_fields must be an object")
        try:
            ocr_text = document_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise _fail(document_path, f"cannot read document text: {exc}") from exc
        if not ocr_text.strip():
            raise _fail(document_path, "document text must be non-empty")

        amounts: list[Decimal] = []
        normalized_journals: list[dict[str, Any]] = []
        for index, entry in enumerate(journals):
            debit = _decimal(
                entry.get("debit"),
                f"expected_journal_entries[{index}].debit",
                case_path,
            )
            credit = _decimal(
                entry.get("credit"), f"expected_journal_entries[{index}].credit", case_path
            )
            account = _required_text(
                entry.get("account"), f"expected_journal_entries[{index}].account", case_path
            )
            amounts.extend((debit, credit))
            normalized_journals.append(
                {
                    "account": account,
                    "debit": debit,
                    "credit": credit,
                    "memo": entry.get("memo"),
                }
            )
        normalized_fields: dict[str, Any] = {}
        for key, value in expected_fields.items():
            if key.endswith(("_amount", "_balance", "_total")) or key in {
                "amount",
                "total",
                "subtotal",
            }:
                amount = _decimal(value, f"expected_fields.{key}", case_path)
                amounts.append(amount)
                normalized_fields[key] = amount
            else:
                normalized_fields[key] = value

        cases.append(
            FinBalanceCase(
                case_id=case_id,
                industry=industry,
                complexity=complexity,
                document_path=document_path,
                ocr_text=ocr_text,
                expected_journal_entries=tuple(normalized_journals),
                contradiction_labels=tuple(item.strip() for item in contradictions),
                expected_fields=normalized_fields,
                amounts=tuple(amounts),
                provenance_sha256=_digest(case_path),
            )
        )
    return tuple(cases)
