"""Tests for DatasetCase → TrainingExample conversion and the train_ml pipeline."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from evaluation.train_ml import train_ml_pipeline, write_synthetic_pairs
from evaluation.train_ml.pipeline import evaluate_generalization, load_training_examples
from services.ml.calibration import ThresholdConstraint
from services.ml.datasets import (
    DatasetFormatError,
    load_custom_benchmark,
    training_examples_from_cases,
)
from services.ml.model import load_model, rank_candidates
from services.ml.training import train_baselines


def test_training_examples_from_custom_pairs(tmp_path: Path) -> None:
    path = write_synthetic_pairs(tmp_path / "pairs.jsonl", worlds=6)
    cases = load_custom_benchmark(path)
    examples = training_examples_from_cases(cases)

    assert len(examples) == 18
    assert sum(example.is_match for example in examples) == 6
    assert sum(example.is_hard_negative for example in examples) == 6
    assert isinstance(examples[0].candidate.sources[0].amount, Decimal)
    assert examples[0].generator_seed
    assert examples[0].entity_id
    assert examples[0].scenario_id


def test_pair_conversion_rejects_non_custom_and_invalid_truth(tmp_path: Path) -> None:
    path = write_synthetic_pairs(tmp_path / "pairs.jsonl", worlds=6)
    cases = list(load_custom_benchmark(path))
    broken = cases[0]
    object.__setattr__(
        broken,
        "ground_truth",
        {**dict(broken.ground_truth), "is_match": "yes"},
    )
    with pytest.raises(DatasetFormatError, match="is_match"):
        training_examples_from_cases([broken])


def test_train_ml_pipeline_calibrates_generalizes_and_writes_artifact(tmp_path: Path) -> None:
    dataset = write_synthetic_pairs(tmp_path / "pairs.jsonl", worlds=18)
    artifact_dir = tmp_path / "artifact"
    result = train_ml_pipeline(
        dataset,
        artifact_dir,
        seed=7,
        model_version="phase5-test-pipeline",
        review_constraint=ThresholdConstraint(
            max_false_positive_rate=0.35,
            max_false_positive_exposure=Decimal(2000),
        ),
    )

    assert result.review_gate_passed is True
    assert result.generalization.passes_constraints is True
    assert result.generalization.rows > 0
    assert result.thresholds["candidate"] == result.thresholds["review"]
    assert (artifact_dir / "model.joblib").exists()
    assert (artifact_dir / "model.json").exists()

    model, metadata = load_model(artifact_dir)
    assert metadata["model_version"] == "phase5-test-pipeline"
    assert metadata["review_gate_passed"] is True
    assert metadata["training_dataset_hash"] == result.training_dataset_hash
    assert set(model) == {"estimator", "calibrator"}

    examples = load_training_examples(dataset)
    sample = [example.candidate for example in examples[:4]]
    ranked = rank_candidates(artifact_dir, sample)
    assert len(ranked) == 4
    assert all(row["automatic_action_eligible"] is False for row in ranked)


def test_generalization_uses_frozen_thresholds_on_held_out_worlds(tmp_path: Path) -> None:
    dataset = write_synthetic_pairs(tmp_path / "pairs.jsonl", worlds=18)
    examples = load_training_examples(dataset)
    baselines = train_baselines(examples, seed=11)
    estimator = baselines.models[baselines.best_model_name]

    from evaluation.train_ml.pipeline import _amounts, _labels, _matrix
    from services.ml.calibration import calibrate_held_out

    calibration = calibrate_held_out(
        estimator,
        _matrix(baselines.split.validation),
        _labels(baselines.split.validation),
        _amounts(baselines.split.validation),
        auto_match_constraint=ThresholdConstraint(0.0, Decimal(0)),
        review_constraint=ThresholdConstraint(0.35, Decimal(2000)),
        seed=11,
    )
    metrics = evaluate_generalization(
        estimator=estimator,
        calibrator=calibration.calibrator,
        examples=baselines.split.test,
        thresholds=calibration.thresholds,
        auto_match_constraint=ThresholdConstraint(0.0, Decimal(0)),
        review_constraint=ThresholdConstraint(0.35, Decimal(2000)),
    )
    assert metrics.rows == len(baselines.split.test)
    assert metrics.hard_negative_count >= 0
    assert metrics.passes_constraints is True


def test_cli_writes_synthetic_dataset_and_report(tmp_path: Path) -> None:
    from evaluation.train_ml.__main__ import main

    dataset = tmp_path / "data" / "pairs.jsonl"
    artifact = tmp_path / "artifact"
    report = tmp_path / "metrics.json"
    assert (
        main(
            [
                "--dataset",
                str(dataset),
                "--artifact-dir",
                str(artifact),
                "--report",
                str(report),
                "--write-synthetic",
                "--synthetic-worlds",
                "18",
                "--seed",
                "5",
                "--review-max-fp-rate",
                "0.35",
                "--review-max-fp-exposure",
                "2000",
            ]
        )
        == 0
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["review_gate_passed"] is True
    assert payload["generalization"]["passes_constraints"] is True
    assert dataset.exists()


def test_cli_demo_uses_deterministic_local_outputs(tmp_path: Path, monkeypatch) -> None:
    from evaluation.train_ml.__main__ import main

    monkeypatch.chdir(tmp_path)
    assert main(["--demo", "--synthetic-worlds", "18", "--seed", "5"]) == 0
    report = tmp_path / ".data" / "phase5-demo" / "metrics.json"
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["review_gate_passed"] is True
    assert (tmp_path / ".data" / "phase5-demo" / "artifact" / "model.json").exists()
