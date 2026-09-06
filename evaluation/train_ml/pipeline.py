"""Phase 5 end-to-end ML training pipeline (Agent F ownership).

Loads custom pair JSONL → TrainingExample → grouped split → baselines →
held-out calibration → artifact → generalization metrics on the test worlds.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from services.ml.artifact import save_model_artifact
from services.ml.calibration import ThresholdConstraint, calibrate_held_out
from services.ml.datasets import load_custom_benchmark
from services.ml.datasets.examples import training_examples_from_cases
from services.ml.features import FEATURE_VERSION, feature_vector, totals
from services.ml.selection import REVIEW_POLICY
from services.ml.training import BaselineResult, TrainingExample, train_baselines


@dataclass(frozen=True)
class GeneralizationMetrics:
    rows: int
    auto_match_selected: int
    auto_match_false_positives: int
    auto_match_false_positive_rate: float | None
    review_selected: int
    review_false_positives: int
    review_false_positive_rate: float | None
    hard_negative_count: int
    hard_negative_false_positives: int
    hard_negative_false_positive_rate: float
    passes_constraints: bool


@dataclass(frozen=True)
class TrainMlResult:
    artifact_directory: Path
    model_version: str
    best_model_name: str
    training_dataset_hash: str
    thresholds: dict[str, float | None]
    validation_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    calibration_metrics: dict[str, Any]
    generalization: GeneralizationMetrics
    review_gate_passed: bool


def dataset_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exposure_amount(example: TrainingExample) -> Decimal:
    source_total, target_total = totals(example.candidate)
    return max(abs(source_total), abs(target_total), Decimal("0.01"))


def load_training_examples(path: str | Path) -> list[TrainingExample]:
    cases = load_custom_benchmark(path)
    return training_examples_from_cases(cases)


def _matrix(examples: Sequence[TrainingExample]):
    return [feature_vector(example.candidate) for example in examples]


def _labels(examples: Sequence[TrainingExample]) -> list[int]:
    return [int(example.is_match) for example in examples]


def _amounts(examples: Sequence[TrainingExample]) -> list[Decimal]:
    return [exposure_amount(example) for example in examples]


def _calibrated_probabilities(estimator, calibrator, examples: Sequence[TrainingExample]):
    import numpy as np

    raw = np.asarray(estimator.predict_proba(_matrix(examples)), dtype=float)[:, 1]
    clipped = np.clip(raw, 1e-8, 1 - 1e-8)
    logits = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    return calibrator.predict_proba(logits)[:, 1]


def evaluate_generalization(
    *,
    estimator,
    calibrator,
    examples: Sequence[TrainingExample],
    thresholds: Mapping[str, float | None],
    auto_match_constraint: ThresholdConstraint,
    review_constraint: ThresholdConstraint,
) -> GeneralizationMetrics:
    """Score held-out worlds with frozen thresholds; never retunes on this set."""
    if not examples:
        raise ValueError("Generalization evaluation requires examples")
    probabilities = _calibrated_probabilities(estimator, calibrator, examples)
    labels = _labels(examples)
    amounts = _amounts(examples)
    hard = [example.is_hard_negative for example in examples]

    auto_threshold = thresholds.get("auto_match")
    review_threshold = thresholds.get("review")

    auto_selected = (
        [prob >= auto_threshold for prob in probabilities]
        if auto_threshold is not None
        else [False] * len(probabilities)
    )
    review_selected = (
        [prob >= review_threshold for prob in probabilities]
        if review_threshold is not None
        else [False] * len(probabilities)
    )

    auto_fp = sum(
        1 for chosen, label in zip(auto_selected, labels, strict=True) if chosen and label == 0
    )
    review_fp = sum(
        1 for chosen, label in zip(review_selected, labels, strict=True) if chosen and label == 0
    )
    auto_count = sum(auto_selected)
    review_count = sum(review_selected)
    hard_count = sum(hard)
    hard_fp = sum(
        1
        for chosen, is_hard in zip(review_selected, hard, strict=True)
        if chosen and is_hard
    )

    auto_rate = (auto_fp / auto_count) if auto_count else None
    review_rate = (review_fp / review_count) if review_count else None
    auto_exposure = sum(
        (
            amount
            for chosen, label, amount in zip(auto_selected, labels, amounts, strict=True)
            if chosen and label == 0
        ),
        Decimal(0),
    )
    review_exposure = sum(
        (
            amount
            for chosen, label, amount in zip(review_selected, labels, amounts, strict=True)
            if chosen and label == 0
        ),
        Decimal(0),
    )

    passes = True
    if auto_threshold is not None:
        passes = passes and auto_fp == 0 and auto_exposure <= auto_match_constraint.max_false_positive_exposure
        if auto_rate is not None:
            passes = passes and auto_rate <= auto_match_constraint.max_false_positive_rate
    if review_threshold is not None and review_count:
        passes = passes and review_rate is not None
        passes = passes and review_rate <= review_constraint.max_false_positive_rate
        passes = passes and review_exposure <= review_constraint.max_false_positive_exposure

    return GeneralizationMetrics(
        rows=len(examples),
        auto_match_selected=auto_count,
        auto_match_false_positives=auto_fp,
        auto_match_false_positive_rate=auto_rate,
        review_selected=review_count,
        review_false_positives=review_fp,
        review_false_positive_rate=review_rate,
        hard_negative_count=hard_count,
        hard_negative_false_positives=hard_fp,
        hard_negative_false_positive_rate=(hard_fp / hard_count) if hard_count else 0.0,
        passes_constraints=passes,
    )


def train_ml_pipeline(
    dataset_path: str | Path,
    artifact_directory: str | Path,
    *,
    seed: int = 42,
    model_version: str = "phase5-ml-v1",
    auto_match_constraint: ThresholdConstraint | None = None,
    review_constraint: ThresholdConstraint | None = None,
    require_generalization: bool = True,
) -> TrainMlResult:
    """Fit baselines, calibrate on validation worlds, and persist a review-only artifact."""
    dataset_path = Path(dataset_path)
    artifact_directory = Path(artifact_directory)
    auto_match_constraint = auto_match_constraint or ThresholdConstraint(
        max_false_positive_rate=0.0,
        max_false_positive_exposure=Decimal("0"),
    )
    review_constraint = review_constraint or ThresholdConstraint(
        max_false_positive_rate=0.25,
        max_false_positive_exposure=Decimal("500"),
    )

    examples = load_training_examples(dataset_path)
    digest = dataset_hash(dataset_path)
    baselines = train_baselines(examples, seed=seed)
    estimator = baselines.models[baselines.best_model_name]

    calibration = calibrate_held_out(
        estimator,
        _matrix(baselines.split.validation),
        _labels(baselines.split.validation),
        _amounts(baselines.split.validation),
        auto_match_constraint=auto_match_constraint,
        review_constraint=review_constraint,
        seed=seed,
    )

    relationships = sorted(
        {
            "+".join(sorted(record.record_type for record in example.candidate.sources))
            + "->"
            + "+".join(sorted(record.record_type for record in example.candidate.targets))
            for example in examples
        }
    )

    generalization = evaluate_generalization(
        estimator=estimator,
        calibrator=calibration.calibrator,
        examples=baselines.split.test,
        thresholds=calibration.thresholds,
        auto_match_constraint=auto_match_constraint,
        review_constraint=review_constraint,
    )
    review_gate_passed = bool(
        calibration.thresholds["review"] is not None and generalization.passes_constraints
    )
    if require_generalization and not review_gate_passed:
        raise ValueError(
            "Calibration did not generalize to held-out worlds under the configured constraints"
        )

    metrics = {
        "best_model_name": baselines.best_model_name,
        "feature_version": FEATURE_VERSION,
        "validation": {
            name: asdict(value) for name, value in baselines.validation_metrics.items()
        },
        "test": {name: asdict(value) for name, value in baselines.test_metrics.items()},
        "calibration": dict(calibration.metrics),
        "generalization": asdict(generalization),
        "review_policy": dict(REVIEW_POLICY),
    }
    save_model_artifact(
        artifact_directory,
        estimator=estimator,
        calibrator=calibration.calibrator,
        training_dataset_hash=digest,
        seed=seed,
        thresholds=calibration.thresholds,
        metrics=metrics,
        model_version=model_version,
        validated_relationships=relationships,
        review_gate_passed=review_gate_passed,
    )
    return TrainMlResult(
        artifact_directory=artifact_directory,
        model_version=model_version,
        best_model_name=baselines.best_model_name,
        training_dataset_hash=digest,
        thresholds=dict(calibration.thresholds),
        validation_metrics=metrics["validation"],
        test_metrics=metrics["test"],
        calibration_metrics=dict(calibration.metrics),
        generalization=generalization,
        review_gate_passed=review_gate_passed,
    )


def write_metrics_report(result: TrainMlResult, path: str | Path) -> None:
    path = Path(path)
    payload = {
        "artifact_directory": str(result.artifact_directory),
        "model_version": result.model_version,
        "best_model_name": result.best_model_name,
        "training_dataset_hash": result.training_dataset_hash,
        "thresholds": result.thresholds,
        "validation_metrics": result.validation_metrics,
        "test_metrics": result.test_metrics,
        "calibration_metrics": result.calibration_metrics,
        "generalization": asdict(result.generalization),
        "review_gate_passed": result.review_gate_passed,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
