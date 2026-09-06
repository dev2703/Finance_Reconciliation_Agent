"""Strict, offline adapters for ReconRiver, FinRCA-Bench, and local JSONL cases."""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .contracts import DatasetCase, DatasetFormatError, DatasetGrouping, SourceRow

_RECON_COLUMNS = (
    "scenario_id",
    "result_scope",
    "work_key",
    "settlement_batch_id",
    "internal_payment_id",
    "processor_transaction_id",
    "bank_entry_id",
    "expected_outcome",
    "expected_reason_code",
    "expected_difference",
    "explanation",
)
_MONEY_NAMES = {
    "amount",
    "subtotal",
    "total",
    "tax",
    "shipping",
    "unit_price",
    "approval_limit",
    "exchange_rate",
    "debit",
    "credit",
    "opening_balance",
    "closing_balance",
    "total_credits",
    "total_debits",
    "expected_difference",
}


def _fail(path: Path, message: str, line: int | None = None) -> DatasetFormatError:
    location = f"{path}:{line}" if line is not None else str(path)
    return DatasetFormatError(f"{location}: {message}")


def _digest(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise _fail(path, f"cannot read input: {exc}") from exc
    return hashlib.sha256(data).hexdigest()


def _source(path: Path, line: int | None) -> SourceRow:
    return SourceRow(path=path, line=line, sha256=_digest(path))


def _required_text(value: Any, name: str, path: Path, line: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, f"{name} must be a non-empty string", line)
    return value.strip()


def _seed(value: Any, path: Path, name: str = "generator seed") -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(path, f"{name} must be an integer")
    return value


def _is_money_key(key: str) -> bool:
    lowered = key.casefold()
    return lowered in _MONEY_NAMES or lowered.endswith(("_amount", "_balance", "_total"))


def _decimal(value: Any, path: Path, line: int | None, key: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        raise _fail(path, f"{key} must be an exact decimal string or integer", line)
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise _fail(path, f"{key} is not a valid decimal amount", line) from exc
    if not parsed.is_finite():
        raise _fail(path, f"{key} must be finite", line)
    return parsed


def _normalize_money(
    value: Any, path: Path, line: int | None, amounts: list[Decimal], key: str = ""
) -> Any:
    if key and _is_money_key(key) and value not in (None, ""):
        amount = _decimal(value, path, line, key)
        amounts.append(amount)
        return amount
    if isinstance(value, dict):
        return {
            child_key: _normalize_money(child, path, line, amounts, child_key)
            for child_key, child in value.items()
        }
    if isinstance(value, list):
        return [_normalize_money(child, path, line, amounts, key) for child in value]
    return value


def _string_values(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return set().union(*(_string_values(child) for child in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_string_values(child) for child in value), set())
    return set()


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail(path, f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise _fail(path, "top-level value must be an object")
    return value


def _load_jsonl(path: Path) -> list[tuple[int, Mapping[str, Any]]]:
    rows: list[tuple[int, Mapping[str, Any]]] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if not raw.strip():
                    raise _fail(path, "blank JSONL rows are not allowed", line_number)
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise _fail(path, f"invalid JSON: {exc.msg}", line_number) from exc
                if not isinstance(value, dict):
                    raise _fail(path, "row must be an object", line_number)
                rows.append((line_number, value))
    except OSError as exc:
        raise _fail(path, f"cannot read input: {exc}") from exc
    if not rows:
        raise _fail(path, "file contains no cases")
    return rows


def _unique_case_ids(cases: Iterable[DatasetCase], path: Path) -> tuple[DatasetCase, ...]:
    result = tuple(cases)
    seen: set[str] = set()
    for case in result:
        if case.case_id in seen:
            raise _fail(path, f"duplicate case_id {case.case_id!r}")
        seen.add(case.case_id)
    return result


def load_reconriver(root: str | Path) -> tuple[DatasetCase, ...]:
    """Load one ReconRiver scenario directory and verify declared ground-truth checksum."""
    root = Path(root)
    manifest_path = root / "scenario_manifest.json"
    truth_path = root / "expected_reconciliation.csv"
    manifest = _load_json(manifest_path)
    scenario = _required_text(manifest.get("scenario_id"), "scenario_id", manifest_path)
    seed = _seed(manifest.get("random_seed"), manifest_path, "random_seed")
    checksums = manifest.get("file_sha256_checksums")
    if not isinstance(checksums, dict) or not isinstance(
        checksums.get("expected_reconciliation.csv"), str
    ):
        raise _fail(manifest_path, "expected_reconciliation.csv checksum is required")
    if _digest(truth_path) != checksums["expected_reconciliation.csv"]:
        raise _fail(truth_path, "SHA-256 does not match scenario manifest")

    cases: list[DatasetCase] = []
    try:
        with truth_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != _RECON_COLUMNS:
                raise _fail(truth_path, "unexpected or reordered CSV columns", 1)
            for line_number, row in enumerate(reader, start=2):
                if row["scenario_id"] != scenario:
                    raise _fail(truth_path, "row scenario_id differs from manifest", line_number)
                scope = _required_text(row["result_scope"], "result_scope", truth_path, line_number)
                work_key = _required_text(row["work_key"], "work_key", truth_path, line_number)
                label = _required_text(
                    row["expected_outcome"], "expected_outcome", truth_path, line_number
                )
                entity_ids = tuple(
                    dict.fromkeys(
                        value.strip()
                        for key in (
                            "work_key",
                            "settlement_batch_id",
                            "internal_payment_id",
                            "processor_transaction_id",
                            "bank_entry_id",
                        )
                        if (value := row[key]).strip()
                    )
                )
                amounts: list[Decimal] = []
                truth = _normalize_money(dict(row), truth_path, line_number, amounts)
                cases.append(
                    DatasetCase(
                        dataset="reconriver",
                        case_id=f"{scenario}:{scope}:{work_key}",
                        label=label,
                        grouping=DatasetGrouping(scenario, entity_ids, seed),
                        ground_truth=truth,
                        records=(),
                        amounts=tuple(amounts),
                        provenance=(
                            _source(manifest_path, None),
                            _source(truth_path, line_number),
                        ),
                    )
                )
    except OSError as exc:
        raise _fail(truth_path, f"cannot read input: {exc}") from exc
    if not cases:
        raise _fail(truth_path, "file contains no ground-truth rows")
    return _unique_case_ids(cases, truth_path)


def load_finrca(root: str | Path) -> tuple[DatasetCase, ...]:
    """Load a FinRCA-Bench root with ground truth, evidence, and resolved seed."""
    root = Path(root)
    truth_path = root / "rca_ground_truth.jsonl"
    config_path = root / "resolved_config.yaml"
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise _fail(config_path, f"invalid YAML: {exc}") from exc
    if not isinstance(config, dict):
        raise _fail(config_path, "top-level value must be an object")
    seed = _seed(config.get("seed"), config_path, "seed")

    evidence_paths = sorted(root.glob("*/case_entity_records.jsonl"))
    direct_evidence = root / "case_entity_records.jsonl"
    if direct_evidence.exists():
        evidence_paths.insert(0, direct_evidence)
    if not evidence_paths:
        raise _fail(root, "no case_entity_records.jsonl evidence files found")
    evidence: dict[str, list[tuple[Path, int, Mapping[str, Any]]]] = {}
    evidence_splits: dict[str, set[str]] = {}
    for evidence_path in evidence_paths:
        split_name = evidence_path.parent.name if evidence_path.parent != root else ""
        for line_number, row in _load_jsonl(evidence_path):
            case_id = _required_text(row.get("case_id"), "case_id", evidence_path, line_number)
            table = _required_text(row.get("table"), "table", evidence_path, line_number)
            record = row.get("record")
            if not isinstance(record, dict):
                raise _fail(evidence_path, "record must be an object", line_number)
            evidence.setdefault(case_id, []).append(
                (evidence_path, line_number, {"table": table, "record": record})
            )
            evidence_splits.setdefault(case_id, set()).add(split_name)

    cases: list[DatasetCase] = []
    truth_ids: set[str] = set()
    for line_number, row in _load_jsonl(truth_path):
        case_id = _required_text(row.get("case_id"), "case_id", truth_path, line_number)
        if case_id in truth_ids:
            raise _fail(truth_path, f"duplicate case_id {case_id!r}", line_number)
        truth_ids.add(case_id)
        label = _required_text(row.get("failure_type"), "failure_type", truth_path, line_number)
        scenario = _required_text(
            row.get("scenario_variant"), "scenario_variant", truth_path, line_number
        )
        vendor = _required_text(
            row.get("group_vendor_id"), "group_vendor_id", truth_path, line_number
        )
        primary = row.get("primary_entity")
        affected = row.get("affected_entities")
        if not isinstance(primary, dict) or not isinstance(affected, list):
            raise _fail(
                truth_path, "primary_entity and affected_entities are required", line_number
            )
        primary_id = _required_text(primary.get("id"), "primary_entity.id", truth_path, line_number)
        affected_ids = []
        for position, entity in enumerate(affected):
            if not isinstance(entity, dict):
                raise _fail(
                    truth_path, f"affected_entities[{position}] must be an object", line_number
                )
            affected_ids.append(
                _required_text(
                    entity.get("id"), f"affected_entities[{position}].id", truth_path, line_number
                )
            )
        case_evidence = evidence.get(case_id)
        if not case_evidence:
            raise _fail(truth_path, f"case {case_id!r} has no model-visible evidence", line_number)
        truth_split = _required_text(row.get("split"), "split", truth_path, line_number)
        observed_splits = evidence_splits[case_id] - {""}
        if len(observed_splits) > 1 or (observed_splits and observed_splits != {truth_split}):
            raise _fail(
                truth_path,
                f"case {case_id!r} evidence split conflicts with ground truth",
                line_number,
            )
        evidence_ids = row.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise _fail(truth_path, "evidence_ids must be a non-empty list", line_number)
        record_values = _string_values([item[2] for item in case_evidence])
        missing = [
            item for item in evidence_ids if not isinstance(item, str) or item not in record_values
        ]
        if missing:
            raise _fail(
                truth_path,
                f"evidence_ids do not resolve in case evidence: {missing!r}",
                line_number,
            )

        amounts: list[Decimal] = []
        normalized_truth = _normalize_money(dict(row), truth_path, line_number, amounts)
        normalized_records = tuple(
            _normalize_money(dict(item), evidence_file, evidence_line, amounts)
            for evidence_file, evidence_line, item in case_evidence
        )
        cases.append(
            DatasetCase(
                dataset="finrca",
                case_id=case_id,
                label=label,
                grouping=DatasetGrouping(
                    scenario,
                    tuple(dict.fromkeys((vendor, primary_id, *affected_ids))),
                    seed,
                ),
                ground_truth=normalized_truth,
                records=normalized_records,
                amounts=tuple(amounts),
                provenance=(
                    _source(config_path, None),
                    _source(truth_path, line_number),
                    *(_source(item[0], item[1]) for item in case_evidence),
                ),
            )
        )
    unknown = sorted(set(evidence) - truth_ids)
    if unknown:
        raise _fail(root, f"evidence exists for unknown cases: {unknown!r}")
    return tuple(cases)


def load_custom_benchmark(path: str | Path) -> tuple[DatasetCase, ...]:
    """Load repository custom JSONL cases using the documented explicit contract.

    Required row fields are ``case_id``, ``scenario_id``, ``generator_seed``,
    ``group_entity_ids``, ``label``, ``ground_truth``, and ``records``.
    """
    path = Path(path)
    cases: list[DatasetCase] = []
    for line_number, row in _load_jsonl(path):
        allowed = {
            "case_id",
            "scenario_id",
            "generator_seed",
            "group_entity_ids",
            "label",
            "ground_truth",
            "records",
        }
        if set(row) != allowed:
            raise _fail(path, f"row fields must be exactly {sorted(allowed)!r}", line_number)
        case_id = _required_text(row["case_id"], "case_id", path, line_number)
        scenario = _required_text(row["scenario_id"], "scenario_id", path, line_number)
        label = _required_text(row["label"], "label", path, line_number)
        seed = _seed(row["generator_seed"], path)
        entity_ids = row["group_entity_ids"]
        if (
            not isinstance(entity_ids, list)
            or not entity_ids
            or any(not isinstance(item, str) or not item.strip() for item in entity_ids)
        ):
            raise _fail(path, "group_entity_ids must be a non-empty string list", line_number)
        normalized_ids = tuple(item.strip() for item in entity_ids)
        if len(set(normalized_ids)) != len(normalized_ids):
            raise _fail(path, "group_entity_ids must be unique", line_number)
        if not isinstance(row["ground_truth"], dict) or not isinstance(row["records"], list):
            raise _fail(
                path, "ground_truth must be an object and records must be a list", line_number
            )
        if not row["records"] or any(not isinstance(item, dict) for item in row["records"]):
            raise _fail(path, "records must contain one or more objects", line_number)
        amounts: list[Decimal] = []
        truth = _normalize_money(row["ground_truth"], path, line_number, amounts)
        records = tuple(
            _normalize_money(item, path, line_number, amounts) for item in row["records"]
        )
        cases.append(
            DatasetCase(
                dataset="custom",
                case_id=case_id,
                label=label,
                grouping=DatasetGrouping(scenario, normalized_ids, seed),
                ground_truth=truth,
                records=records,
                amounts=tuple(amounts),
                provenance=(_source(path, line_number),),
            )
        )
    return _unique_case_ids(cases, path)
