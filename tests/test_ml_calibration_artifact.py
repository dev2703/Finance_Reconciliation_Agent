import hashlib
import json
from decimal import Decimal

import numpy as np
import pytest

from services.ml.artifact import save_model_artifact
from services.ml.calibration import ThresholdConstraint, calibrate_held_out
from services.ml.features import FEATURE_NAMES, FEATURE_VERSION
from services.ml.model import load_model
from services.ml.selection import REVIEW_POLICY


class FixedEstimator:
    def __init__(self, probabilities):
        self.probabilities = np.asarray(probabilities, dtype=float)

    def predict_proba(self, features):
        assert len(features) == len(self.probabilities)
        return np.column_stack((1 - self.probabilities, self.probabilities))


def constraints(rate: float, exposure: str) -> ThresholdConstraint:
    return ThresholdConstraint(rate, Decimal(exposure))


def test_held_out_platt_calibration_improves_overconfident_probabilities():
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    estimator = FixedEstimator([0.45, 0.55, 0.65, 0.75, 0.85, 0.90, 0.95, 0.99])
    result = calibrate_held_out(
        estimator,
        [[index] for index in range(8)],
        labels,
        [Decimal(100)] * 8,
        auto_match_constraint=constraints(0, "0"),
        review_constraint=constraints(0.25, "100"),
        seed=17,
    )

    assert result.metrics["brier_after"] < result.metrics["brier_before"]
    assert result.metrics["log_loss_after"] < result.metrics["log_loss_before"]
    assert result.thresholds["auto_match"] >= result.thresholds["review"]
    assert result.thresholds["candidate"] == result.thresholds["review"]
    assert result.thresholds["unresolved"] < result.thresholds["review"]
    assert result.metrics["auto_match_false_positive_exposure"] == "0"


def test_financial_exposure_constraint_changes_threshold_deterministically():
    estimator = FixedEstimator([0.99, 0.98, 0.97, 0.20])
    kwargs = dict(
        estimator=estimator,
        features=[[0], [1], [2], [3]],
        labels=[1, 0, 1, 0],
        amounts=[Decimal(10), Decimal(1000), Decimal(10), Decimal(1)],
        auto_match_constraint=constraints(0.50, "0"),
        review_constraint=constraints(0.50, "1000"),
        seed=3,
    )
    first = calibrate_held_out(**kwargs)
    second = calibrate_held_out(**kwargs)

    assert first.thresholds == second.thresholds
    assert first.probabilities == second.probabilities
    assert first.metrics["auto_match_false_positive_exposure"] == "0"
    assert first.metrics["review_false_positive_exposure"] == "1000"


def test_calibration_rejects_invalid_inputs_and_fails_closed_without_valid_gate():
    estimator = FixedEstimator([0.2, 0.8])
    with pytest.raises(ValueError, match="both binary classes"):
        calibrate_held_out(
            estimator,
            [[0], [1]],
            [1, 1],
            [Decimal(1), Decimal(1)],
            auto_match_constraint=constraints(0, "0"),
            review_constraint=constraints(0, "0"),
            seed=1,
        )
    with pytest.raises(ValueError, match="non-negative"):
        constraints(0, "-0.01")

    fail_closed = calibrate_held_out(
        FixedEstimator([0.99, 0.90, 0.80, 0.10]),
        [[0], [1], [2], [3]],
        [0, 1, 1, 0],
        [Decimal(100), Decimal(1), Decimal(1), Decimal(1)],
        auto_match_constraint=constraints(0, "0"),
        review_constraint=constraints(0, "0"),
        seed=1,
    )
    assert fail_closed.thresholds == {
        "auto_match": None,
        "candidate": None,
        "review": None,
        "unresolved": None,
    }


def test_artifact_round_trip_checksum_and_reproducibility(tmp_path):
    estimator = FixedEstimator([0.2, 0.8])
    calibrated = calibrate_held_out(
        estimator,
        [[0], [1]],
        [0, 1],
        [Decimal(10), Decimal(20)],
        auto_match_constraint=constraints(0, "0"),
        review_constraint=constraints(0, "0"),
        seed=11,
    )
    common = dict(
        estimator=estimator,
        calibrator=calibrated.calibrator,
        training_dataset_hash=hashlib.sha256(b"held-out-dataset").hexdigest(),
        seed=11,
        thresholds=calibrated.thresholds,
        metrics=calibrated.metrics,
        model_version="phase5-test-v1",
        validated_relationships=["settlement->bank", "payment->settlement"],
        review_gate_passed=True,
    )
    first_metadata = save_model_artifact(tmp_path / "first", **common)
    second_metadata = save_model_artifact(tmp_path / "second", **common)
    loaded, stored = load_model(tmp_path / "first")

    assert set(loaded) == {"estimator", "calibrator"}
    assert stored == first_metadata
    assert first_metadata == second_metadata
    assert first_metadata["feature_names"] == list(FEATURE_NAMES)
    assert first_metadata["feature_version"] == FEATURE_VERSION
    assert first_metadata["review_policy"] == REVIEW_POLICY
    assert first_metadata["validated_relationships"] == [
        "payment->settlement",
        "settlement->bank",
    ]
    assert json.loads((tmp_path / "first" / "model.json").read_text()) == first_metadata

    artifact = tmp_path / "first" / "model.joblib"
    artifact.write_bytes(artifact.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_model(tmp_path / "first")


def test_artifact_rejects_unordered_or_non_finite_thresholds(tmp_path):
    estimator = FixedEstimator([0.2, 0.8])
    with pytest.raises(ValueError, match="at least"):
        save_model_artifact(
            tmp_path,
            estimator=estimator,
            calibrator=estimator,
            training_dataset_hash="a" * 64,
            seed=1,
            thresholds={
                "auto_match": 0.8,
                "candidate": 0.9,
                "review": 0.9,
                "unresolved": 0.7,
            },
            metrics={},
            model_version="v1",
            validated_relationships=[],
            review_gate_passed=False,
        )
