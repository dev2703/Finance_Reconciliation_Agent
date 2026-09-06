"""ReconRiver matching benchmark runner."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from evaluation.contracts import CasePrediction, SuiteMetrics
from evaluation.metrics import (
    accuracy,
    binary_detection_metrics,
    cost_metrics,
    label_match_metrics,
    risk_metrics,
)
from evaluation.runners.predictions import load_predictions, require_predictions_for_cases
from services.ml.datasets import load_reconriver
from services.ml.datasets.contracts import DatasetCase

RECONRIVER_SCENARIOS = (
    "clean-settlement",
    "mixed-exceptions",
    "month-end-close",
    "failure-recovery",
)

_MATCHED_LABELS = {"MATCHED", "CLEAN_SETTLEMENT", "RECONCILED"}
_HARD_NEGATIVE_LABELS = {"HARD_NEGATIVE", "LEGITIMATE", "NO_FAILURE"}


def discover_reconriver_scenarios(root: str | Path) -> tuple[Path, ...]:
    root = Path(root)
    discovered: list[Path] = []
    for name in RECONRIVER_SCENARIOS:
        candidate = root / name
        if candidate.is_dir() and (candidate / "scenario_manifest.json").exists():
            discovered.append(candidate)
    if not discovered:
        raise FileNotFoundError(
            f"no ReconRiver scenarios found under {root}; expected one of {RECONRIVER_SCENARIOS}"
        )
    return tuple(discovered)


def _case_amount(case: DatasetCase) -> Decimal:
    if case.amounts:
        return abs(case.amounts[0])
    difference = case.ground_truth.get("expected_difference")
    if isinstance(difference, Decimal):
        return abs(difference)
    return Decimal(0)


def _is_exception_label(label: str) -> bool:
    return label.upper() not in _MATCHED_LABELS and label.upper() not in _HARD_NEGATIVE_LABELS


def score_reconriver(
    cases: Sequence[DatasetCase],
    predictions: Sequence[CasePrediction],
    *,
    suite: str = "reconriver",
) -> SuiteMetrics:
    indexed = require_predictions_for_cases(predictions, [case.case_id for case in cases])
    ordered = [indexed[case.case_id] for case in cases]

    expected_labels = [case.label for case in cases]
    predicted_labels = [item.predicted_label for item in ordered]
    classification = label_match_metrics(expected_labels, predicted_labels)

    expected_positive = [_is_exception_label(case.label) for case in cases]
    predicted_positive = []
    for case, prediction in zip(cases, ordered, strict=True):
        if prediction.detected_exception is not None:
            predicted_positive.append(prediction.detected_exception)
        else:
            predicted_positive.append(
                prediction.predicted_label is not None
                and _is_exception_label(prediction.predicted_label)
            )
    detection = binary_detection_metrics(expected_positive, predicted_positive)

    hard_negative_count = 0
    hard_negative_fp = 0
    auto_resolved = 0
    fp_amounts: list[Decimal] = []
    fn_amounts: list[Decimal] = []
    correct_amounts: list[Decimal] = []
    for case, prediction in zip(cases, ordered, strict=True):
        amount = prediction.amount if prediction.amount > 0 else _case_amount(case)
        label_upper = case.label.upper()
        is_hard_negative = label_upper in _HARD_NEGATIVE_LABELS
        correct = prediction.predicted_label == case.label
        if is_hard_negative:
            hard_negative_count += 1
            if (
                prediction.auto_resolved
                or (prediction.detected_exception is True)
                or (
                    prediction.predicted_label is not None
                    and prediction.predicted_label.upper() not in _HARD_NEGATIVE_LABELS
                )
            ):
                hard_negative_fp += 1
                fp_amounts.append(amount)
        if prediction.auto_resolved:
            auto_resolved += 1
            if not correct:
                fp_amounts.append(amount)
        if correct:
            correct_amounts.append(amount)
        elif _is_exception_label(case.label) and (
            prediction.predicted_label is None
            or prediction.predicted_label.upper() in _MATCHED_LABELS
        ):
            fn_amounts.append(amount)

    outcome_correct = sum(
        1
        for case, prediction in zip(cases, ordered, strict=True)
        if prediction.predicted_label == case.label
    )

    return SuiteMetrics(
        suite=suite,
        case_count=len(cases),
        classification=classification,
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
            "scenario_ids": sorted({case.grouping.scenario for case in cases}),
            "outcome_accuracy": format(accuracy(outcome_correct, len(cases)), "f"),
            "exception_detection_precision": format(detection.precision, "f"),
            "exception_detection_recall": format(detection.recall, "f"),
            "exception_detection_f1": format(detection.f1, "f"),
        },
    )


def run_reconriver(
    root: str | Path,
    predictions_path: str | Path,
    *,
    suite: str = "reconriver",
) -> tuple[SuiteMetrics, tuple[CasePrediction, ...], tuple[DatasetCase, ...]]:
    """Load all available ReconRiver scenarios and score one prediction file."""
    root = Path(root)
    scenario_dirs = discover_reconriver_scenarios(root)
    cases: list[DatasetCase] = []
    for scenario_dir in scenario_dirs:
        cases.extend(load_reconriver(scenario_dir))
    predictions = load_predictions(predictions_path)
    metrics = score_reconriver(cases, predictions, suite=suite)
    return metrics, predictions, tuple(cases)
