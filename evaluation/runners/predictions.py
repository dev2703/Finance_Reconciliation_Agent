"""Prediction JSONL helpers shared by evaluation runners."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from evaluation.contracts import CasePrediction


class PredictionFormatError(ValueError):
    """Raised when a prediction file cannot be interpreted unambiguously."""


def _fail(path: Path, message: str, line: int | None = None) -> PredictionFormatError:
    location = f"{path}:{line}" if line is not None else str(path)
    return PredictionFormatError(f"{location}: {message}")


def _decimal(value: Any, name: str, path: Path, line: int) -> Decimal:
    if value is None:
        return Decimal(0)
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        raise _fail(path, f"{name} must be an exact decimal string or integer", line)
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _fail(path, f"{name} is not a valid decimal", line) from exc
    if not parsed.is_finite() or parsed < 0:
        raise _fail(path, f"{name} must be finite and non-negative", line)
    return parsed


def _optional_bool(value: Any, name: str, path: Path, line: int) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _fail(path, f"{name} must be a boolean when present", line)
    return value


def _string_list(value: Any, name: str, path: Path, line: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise _fail(path, f"{name} must be a list of non-empty strings", line)
    return tuple(item.strip() for item in value)


def load_predictions(path: str | Path) -> tuple[CasePrediction, ...]:
    """Load UTF-8 JSONL predictions used by offline benchmark packs."""
    path = Path(path)
    predictions: list[CasePrediction] = []
    seen: set[str] = set()
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    raise _fail(path, "blank JSONL rows are not allowed", line_number)
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise _fail(path, f"invalid JSON: {exc.msg}", line_number) from exc
                if not isinstance(row, dict):
                    raise _fail(path, "row must be an object", line_number)
                case_id = row.get("case_id")
                if not isinstance(case_id, str) or not case_id.strip():
                    raise _fail(path, "case_id must be a non-empty string", line_number)
                case_id = case_id.strip()
                if case_id in seen:
                    raise _fail(path, f"duplicate case_id {case_id!r}", line_number)
                seen.add(case_id)
                journals = row.get("journal_entries") or []
                if not isinstance(journals, list) or any(
                    not isinstance(item, dict) for item in journals
                ):
                    raise _fail(path, "journal_entries must be a list of objects", line_number)
                parsed_fields = row.get("parsed_fields") or {}
                if not isinstance(parsed_fields, dict):
                    raise _fail(path, "parsed_fields must be an object", line_number)
                tokens = row.get("llm_tokens", 0)
                if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
                    raise _fail(path, "llm_tokens must be a non-negative integer", line_number)
                label = row.get("predicted_label")
                if label is not None and (not isinstance(label, str) or not label.strip()):
                    raise _fail(path, "predicted_label must be a non-empty string", line_number)
                root_cause = row.get("root_cause")
                if root_cause is not None and (
                    not isinstance(root_cause, str) or not root_cause.strip()
                ):
                    raise _fail(path, "root_cause must be a non-empty string", line_number)
                resolution = row.get("resolution")
                if resolution is not None and (
                    not isinstance(resolution, str) or not resolution.strip()
                ):
                    raise _fail(path, "resolution must be a non-empty string", line_number)
                predictions.append(
                    CasePrediction(
                        case_id=case_id,
                        predicted_label=None if label is None else label.strip(),
                        detected_exception=_optional_bool(
                            row.get("detected_exception"), "detected_exception", path, line_number
                        ),
                        root_cause=None if root_cause is None else root_cause.strip(),
                        evidence_ids=_string_list(
                            row.get("evidence_ids"), "evidence_ids", path, line_number
                        ),
                        resolution=None if resolution is None else resolution.strip(),
                        auto_resolved=bool(row.get("auto_resolved", False)),
                        amount=_decimal(row.get("amount"), "amount", path, line_number),
                        latency_ms=_decimal(row.get("latency_ms"), "latency_ms", path, line_number),
                        llm_tokens=tokens,
                        estimated_cost=_decimal(
                            row.get("estimated_cost"), "estimated_cost", path, line_number
                        ),
                        journal_entries=tuple(journals),
                        contradiction_ids=_string_list(
                            row.get("contradiction_ids"), "contradiction_ids", path, line_number
                        ),
                        parsed_fields=parsed_fields,
                    )
                )
    except OSError as exc:
        raise _fail(path, f"cannot read predictions: {exc}") from exc
    if not predictions:
        raise _fail(path, "file contains no predictions")
    return tuple(predictions)


def require_predictions_for_cases(
    predictions: Sequence[CasePrediction],
    case_ids: Sequence[str],
) -> dict[str, CasePrediction]:
    indexed = {item.case_id: item for item in predictions}
    missing = [case_id for case_id in case_ids if case_id not in indexed]
    if missing:
        raise PredictionFormatError(f"missing predictions for cases: {missing!r}")
    extras = sorted(set(indexed) - set(case_ids))
    if extras:
        raise PredictionFormatError(f"predictions exist for unknown cases: {extras!r}")
    return indexed


def serialize_prediction(prediction: CasePrediction) -> Mapping[str, Any]:
    return {
        "case_id": prediction.case_id,
        "predicted_label": prediction.predicted_label,
        "detected_exception": prediction.detected_exception,
        "root_cause": prediction.root_cause,
        "evidence_ids": list(prediction.evidence_ids),
        "resolution": prediction.resolution,
        "auto_resolved": prediction.auto_resolved,
        "amount": format(prediction.amount, "f"),
        "latency_ms": format(prediction.latency_ms, "f"),
        "llm_tokens": prediction.llm_tokens,
        "estimated_cost": format(prediction.estimated_cost, "f"),
        "journal_entries": list(prediction.journal_entries),
        "contradiction_ids": list(prediction.contradiction_ids),
        "parsed_fields": dict(prediction.parsed_fields),
    }
