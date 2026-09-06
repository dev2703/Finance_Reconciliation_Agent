"""Held-out probability calibration and financially constrained thresholds."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss


@dataclass(frozen=True)
class ThresholdConstraint:
    """Maximum tolerated false positives at one operating tier."""

    max_false_positive_rate: float
    max_false_positive_exposure: Decimal

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_false_positive_rate) or not (
            0 <= self.max_false_positive_rate <= 1
        ):
            raise ValueError("max_false_positive_rate must be between zero and one")
        if not self.max_false_positive_exposure.is_finite() or (
            self.max_false_positive_exposure < 0
        ):
            raise ValueError("max_false_positive_exposure must be finite and non-negative")


@dataclass(frozen=True)
class CalibrationResult:
    calibrator: LogisticRegression
    probabilities: tuple[float, ...]
    thresholds: dict[str, float | None]
    metrics: dict[str, float | int | str | None]


def calibrate_held_out(
    estimator,
    features,
    labels,
    amounts,
    *,
    auto_match_constraint: ThresholdConstraint,
    review_constraint: ThresholdConstraint,
    seed: int,
) -> CalibrationResult:
    """Fit Platt scaling on held-out rows and choose deterministic risk gates.

    ``amounts`` represents financial exposure per candidate and is converted through
    ``str`` so accounting values never pass through binary floating-point arithmetic.
    The caller is responsible for supplying a group-held-out calibration set.
    """
    labels_array = np.asarray(labels, dtype=int)
    if labels_array.ndim != 1 or len(labels_array) < 2:
        raise ValueError("Calibration requires at least two held-out rows")
    if set(labels_array.tolist()) != {0, 1}:
        raise ValueError("Calibration labels must contain both binary classes")
    exposure = tuple(_amount(value) for value in amounts)
    if len(exposure) != len(labels_array):
        raise ValueError("Amounts and labels must have equal length")

    raw = _positive_probabilities(estimator, features)
    if len(raw) != len(labels_array):
        raise ValueError("Estimator probabilities and labels must have equal length")
    logits = _logits(raw)
    calibrator = LogisticRegression(random_state=seed, solver="lbfgs")
    calibrator.fit(logits, labels_array)
    calibrated = calibrator.predict_proba(logits)[:, 1]

    auto_threshold = _select_threshold(
        calibrated, labels_array, exposure, auto_match_constraint, lower_bound=None
    )
    review_threshold = _select_threshold(
        calibrated,
        labels_array,
        exposure,
        review_constraint,
        lower_bound=None,
        upper_bound=auto_threshold,
    )
    unresolved_threshold = _unresolved_boundary(calibrated, review_threshold)
    thresholds = {
        "auto_match": auto_threshold,
        "candidate": review_threshold,
        "review": review_threshold,
        "unresolved": unresolved_threshold,
    }
    metrics = _metrics(raw, calibrated, labels_array, exposure, thresholds)
    metrics.update(
        {
            "auto_match_max_false_positive_rate": auto_match_constraint.max_false_positive_rate,
            "auto_match_max_false_positive_exposure": str(
                auto_match_constraint.max_false_positive_exposure
            ),
            "review_max_false_positive_rate": review_constraint.max_false_positive_rate,
            "review_max_false_positive_exposure": str(
                review_constraint.max_false_positive_exposure
            ),
        }
    )
    return CalibrationResult(
        calibrator=calibrator,
        probabilities=tuple(float(value) for value in calibrated),
        thresholds=thresholds,
        metrics=metrics,
    )


def _positive_probabilities(estimator, features) -> np.ndarray:
    values = np.asarray(estimator.predict_proba(features), dtype=float)
    if values.ndim != 2 or values.shape[1] != 2:
        raise ValueError("Estimator must return two-column binary probabilities")
    positive = values[:, 1]
    if not np.all(np.isfinite(positive)) or np.any((positive < 0) | (positive > 1)):
        raise ValueError("Estimator returned invalid probabilities")
    return positive


def _logits(probabilities: np.ndarray) -> np.ndarray:
    clipped = np.clip(probabilities, 1e-8, 1 - 1e-8)
    return np.log(clipped / (1 - clipped)).reshape(-1, 1)


def _amount(value: Decimal | str | int) -> Decimal:
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("Financial exposure amounts must be finite and non-negative")
    return amount


def _select_threshold(
    probabilities: np.ndarray,
    labels: np.ndarray,
    amounts: tuple[Decimal, ...],
    constraint: ThresholdConstraint,
    *,
    lower_bound: float | None,
    upper_bound: float | None = None,
) -> float | None:
    # Ascending candidates make the first passing threshold the maximum-coverage gate.
    candidates = sorted({float(value) for value in probabilities}, reverse=False)
    for threshold in candidates:
        if lower_bound is not None and threshold < lower_bound:
            continue
        if upper_bound is not None and threshold > upper_bound:
            continue
        selected = probabilities >= threshold
        count = int(selected.sum())
        if count == 0:
            continue
        false_positive = selected & (labels == 0)
        rate = int(false_positive.sum()) / count
        exposure = sum(
            (amount for amount, is_false in zip(amounts, false_positive, strict=True) if is_false),
            Decimal(0),
        )
        if (
            rate <= constraint.max_false_positive_rate
            and exposure <= constraint.max_false_positive_exposure
        ):
            return threshold
    return None


def _unresolved_boundary(probabilities: np.ndarray, review: float | None) -> float | None:
    if review is None:
        return None
    below = [float(value) for value in probabilities if value < review]
    return max(below, default=None)


def _metrics(raw, calibrated, labels, amounts, thresholds):
    result: dict[str, float | int | str | None] = {
        "calibration_rows": len(labels),
        "brier_before": float(brier_score_loss(labels, raw)),
        "brier_after": float(brier_score_loss(labels, calibrated)),
        "log_loss_before": float(log_loss(labels, raw, labels=[0, 1])),
        "log_loss_after": float(log_loss(labels, calibrated, labels=[0, 1])),
    }
    for tier in ("auto_match", "review"):
        threshold = thresholds[tier]
        if threshold is None:
            result[f"{tier}_selected"] = 0
            result[f"{tier}_false_positive_rate"] = None
            result[f"{tier}_false_positive_exposure"] = "0"
            continue
        selected = calibrated >= threshold
        false_positive = selected & (labels == 0)
        count = int(selected.sum())
        result[f"{tier}_selected"] = count
        result[f"{tier}_false_positive_rate"] = int(false_positive.sum()) / count
        result[f"{tier}_false_positive_exposure"] = str(
            sum(
                (
                    amount
                    for amount, is_false in zip(amounts, false_positive, strict=True)
                    if is_false
                ),
                Decimal(0),
            )
        )
    return result
