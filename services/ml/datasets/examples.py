"""Convert custom DatasetCase rows into leakage-safe TrainingExample values.

Custom JSONL cases become training pairs when ``ground_truth`` declares match
labels and source/target record IDs. ReconRiver and FinRCA loaders remain
evaluation adapters; they do not invent candidate pairs here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from services.ml.contracts import Candidate, ObservableRecord
from services.ml.training import TrainingExample

from .contracts import DatasetCase, DatasetFormatError


def training_examples_from_cases(cases: Sequence[DatasetCase]) -> list[TrainingExample]:
    """Build labelled candidates from custom pair-shaped DatasetCase values."""
    examples: list[TrainingExample] = []
    for case in cases:
        if case.dataset != "custom":
            raise DatasetFormatError(
                f"{case.case_id}: only custom pair cases convert to TrainingExample"
            )
        examples.append(_example_from_case(case))
    if not examples:
        raise DatasetFormatError("no training examples produced")
    return examples


def _example_from_case(case: DatasetCase) -> TrainingExample:
    truth = case.ground_truth
    is_match = _required_bool(truth, "is_match", case.case_id)
    is_hard_negative = bool(truth.get("is_hard_negative", False))
    if is_hard_negative and is_match:
        raise DatasetFormatError(f"{case.case_id}: hard negative cannot be a match")
    source_ids = _id_list(truth, "source_ids", case.case_id)
    target_ids = _id_list(truth, "target_ids", case.case_id)
    by_id = _records_by_id(case.records, case.case_id)
    sources = [_observable(by_id[record_id], case.case_id) for record_id in source_ids]
    targets = [_observable(by_id[record_id], case.case_id) for record_id in target_ids]
    graph_score = _optional_score(truth.get("graph_score"), case.case_id)
    entity_id = case.grouping.entity_ids[0]
    return TrainingExample(
        candidate=Candidate(
            id=case.case_id,
            sources=sources,
            targets=targets,
            graph_score=graph_score,
        ),
        is_match=is_match,
        generator_seed=str(case.grouping.generator_seed),
        entity_id=entity_id,
        scenario_id=case.grouping.scenario,
        is_hard_negative=is_hard_negative,
    )


def _required_bool(truth: Mapping[str, Any], key: str, case_id: str) -> bool:
    value = truth.get(key)
    if not isinstance(value, bool):
        raise DatasetFormatError(f"{case_id}: ground_truth.{key} must be a boolean")
    return value


def _id_list(truth: Mapping[str, Any], key: str, case_id: str) -> tuple[str, ...]:
    value = truth.get(key)
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise DatasetFormatError(f"{case_id}: ground_truth.{key} must be a non-empty string list")
    normalized = tuple(item.strip() for item in value)
    if len(set(normalized)) != len(normalized):
        raise DatasetFormatError(f"{case_id}: ground_truth.{key} must be unique")
    return normalized


def _records_by_id(
    records: Sequence[Mapping[str, Any]], case_id: str
) -> dict[str, Mapping[str, Any]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise DatasetFormatError(f"{case_id}: every record requires a non-empty id")
        key = record_id.strip()
        if key in by_id:
            raise DatasetFormatError(f"{case_id}: duplicate record id {key!r}")
        by_id[key] = record
    return by_id


def _observable(record: Mapping[str, Any], case_id: str) -> ObservableRecord:
    record_id = str(record["id"]).strip()
    try:
        return ObservableRecord(
            id=record_id,
            record_type=_required_text(record, "record_type", case_id, record_id),
            amount=_required_amount(record, case_id, record_id),
            currency=_required_text(record, "currency", case_id, record_id).upper(),
            record_date=_required_date(record, case_id, record_id),
            reference=_optional_text(record.get("reference")),
            party=_optional_text(record.get("party")),
            description=_optional_text(record.get("description")),
        )
    except (TypeError, ValueError) as exc:
        raise DatasetFormatError(f"{case_id}: record {record_id!r} is invalid: {exc}") from exc


def _required_text(record: Mapping[str, Any], key: str, case_id: str, record_id: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetFormatError(f"{case_id}: record {record_id!r} missing {key}")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional text fields must be strings")
    stripped = value.strip()
    return stripped or None


def _required_amount(record: Mapping[str, Any], case_id: str, record_id: str) -> Decimal:
    amount = record.get("amount")
    if isinstance(amount, Decimal):
        return amount
    if isinstance(amount, bool) or not isinstance(amount, (str, int)):
        raise DatasetFormatError(
            f"{case_id}: record {record_id!r} amount must be Decimal-compatible"
        )
    return Decimal(str(amount))


def _required_date(record: Mapping[str, Any], case_id: str, record_id: str) -> date:
    value = record.get("record_date")
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise DatasetFormatError(f"{case_id}: record {record_id!r} requires record_date")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise DatasetFormatError(
            f"{case_id}: record {record_id!r} has invalid record_date"
        ) from exc


def _optional_score(value: Any, case_id: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        score = value
    elif isinstance(value, bool) or not isinstance(value, (str, int)):
        raise DatasetFormatError(f"{case_id}: graph_score must be a decimal string or integer")
    else:
        score = Decimal(str(value))
    if not score.is_finite() or score < 0 or score > 1:
        raise DatasetFormatError(f"{case_id}: graph_score must be in [0, 1]")
    return score
