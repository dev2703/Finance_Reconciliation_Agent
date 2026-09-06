"""FinRCA exception/RCA benchmark runner."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from evaluation.contracts import CasePrediction, SuiteMetrics
from evaluation.metrics import (
    accuracy,
    binary_detection_metrics,
    cost_metrics,
    mean_set_precision_recall,
    risk_metrics,
)
from evaluation.runners.predictions import load_predictions, require_predictions_for_cases
from services.ml.datasets import load_finrca
from services.ml.datasets.contracts import DatasetCase

_NO_FAILURE_LABELS = {
    "NO_FAILURE",
    "LEGITIMATE",
    "HARD_NEGATIVE",
    "EXACT_MATCH",
    "MATCHED",
    "RECONCILED",
}
_HARD_NEGATIVE_LABELS = {"NO_FAILURE", "LEGITIMATE", "HARD_NEGATIVE"}


def _case_amount(case: DatasetCase) -> Decimal:
    if case.amounts:
        return max(abs(amount) for amount in case.amounts)
    return Decimal(0)


def _expected_evidence(case: DatasetCase) -> tuple[str, ...]:
    evidence_ids = case.ground_truth.get("evidence_ids")
    if isinstance(evidence_ids, list):
        return tuple(str(item) for item in evidence_ids)
    return ()


def _expected_resolution(case: DatasetCase) -> str | None:
    for key in ("resolution", "expected_resolution", "recommended_resolution"):
        value = case.ground_truth.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_failure(label: str) -> bool:
    return label.upper() not in _NO_FAILURE_LABELS


def score_finrca(
    cases: Sequence[DatasetCase],
    predictions: Sequence[CasePrediction],
    *,
    suite: str = "finrca",
) -> SuiteMetrics:
    indexed = require_predictions_for_cases(predictions, [case.case_id for case in cases])
    ordered = [indexed[case.case_id] for case in cases]

    expected_positive = [_is_failure(case.label) for case in cases]
    predicted_positive = []
    for case, prediction in zip(cases, ordered, strict=True):
        if prediction.detected_exception is not None:
            predicted_positive.append(prediction.detected_exception)
        else:
            predicted_positive.append(
                prediction.predicted_label is not None and _is_failure(prediction.predicted_label)
            )
    detection = binary_detection_metrics(expected_positive, predicted_positive)

    root_correct = 0
    root_total = 0
    resolution_correct = 0
    resolution_total = 0
    evidence_pairs: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    hard_negative_count = 0
    hard_negative_fp = 0
    auto_resolved = 0
    fp_amounts: list[Decimal] = []
    fn_amounts: list[Decimal] = []
    correct_amounts: list[Decimal] = []

    for case, prediction in zip(cases, ordered, strict=True):
        amount = prediction.amount if prediction.amount > 0 else _case_amount(case)
        is_hard_negative = case.label.upper() in _HARD_NEGATIVE_LABELS
        detected = (
            prediction.detected_exception
            if prediction.detected_exception is not None
            else (
                prediction.predicted_label is not None
                and _is_failure(prediction.predicted_label)
            )
        )

        expected_root = case.ground_truth.get("root_cause")
        if isinstance(expected_root, str) and expected_root.strip():
            root_total += 1
            if prediction.root_cause == expected_root.strip():
                root_correct += 1

        expected_resolution = _expected_resolution(case)
        if expected_resolution is not None:
            resolution_total += 1
            if prediction.resolution == expected_resolution:
                resolution_correct += 1

        evidence_pairs.append((_expected_evidence(case), prediction.evidence_ids))

        label_ok = prediction.predicted_label == case.label
        if label_ok and detected == _is_failure(case.label):
            correct_amounts.append(amount)

        if is_hard_negative:
            hard_negative_count += 1
            if detected or prediction.auto_resolved:
                hard_negative_fp += 1
                fp_amounts.append(amount)
        elif _is_failure(case.label) and not detected:
            fn_amounts.append(amount)
        elif prediction.auto_resolved and not label_ok:
            fp_amounts.append(amount)

        if prediction.auto_resolved:
            auto_resolved += 1

    evidence_precision, evidence_recall = mean_set_precision_recall(evidence_pairs)

    return SuiteMetrics(
        suite=suite,
        case_count=len(cases),
        classification=detection,
        root_cause_accuracy=accuracy(root_correct, root_total) if root_total else None,
        evidence_precision=evidence_precision,
        evidence_recall=evidence_recall,
        resolution_accuracy=(
            accuracy(resolution_correct, resolution_total) if resolution_total else None
        ),
        risk=risk_metrics(
            hard_negative_count=hard_negative_count,
            hard_negative_false_positives=hard_negative_fp,
            auto_resolved_count=auto_resolved,
            case_count=len(cases),
            false_positive_amounts=fp_amounts,
            false_negative_amounts=fn_amounts,
            correctly_reconciled_amounts=correct_amounts,
        ),
        cost=cost_metrics(ordered),
        extras={
            "failure_types": sorted({case.label for case in cases}),
            "root_cause_scored": root_total,
            "resolution_scored": resolution_total,
        },
    )


def run_finrca(
    root: str | Path,
    predictions_path: str | Path,
    *,
    suite: str = "finrca",
) -> tuple[SuiteMetrics, tuple[CasePrediction, ...], tuple[DatasetCase, ...]]:
    cases = load_finrca(root)
    predictions = load_predictions(predictions_path)
    metrics = score_finrca(cases, predictions, suite=suite)
    return metrics, predictions, cases
