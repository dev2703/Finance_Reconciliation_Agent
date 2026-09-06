"""Deterministic, model.py-compatible ML artifact writing."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import joblib

from .features import FEATURE_NAMES, FEATURE_VERSION
from .selection import REVIEW_POLICY


def save_model_artifact(
    directory: Path,
    *,
    estimator,
    calibrator,
    training_dataset_hash: str,
    seed: int,
    thresholds: Mapping[str, float | None],
    metrics: Mapping[str, object],
    model_version: str,
    validated_relationships: Sequence[str],
    review_gate_passed: bool,
    review_policy: Mapping[str, object] = REVIEW_POLICY,
) -> dict[str, object]:
    """Write model.joblib and canonical model.json, returning stored metadata."""
    _validate_digest(training_dataset_hash, "training_dataset_hash")
    if not model_version.strip():
        raise ValueError("model_version must not be blank")
    required = {"auto_match", "candidate", "review", "unresolved"}
    if set(thresholds) != required:
        raise ValueError(f"thresholds must contain exactly {sorted(required)}")
    _validate_thresholds(thresholds)
    relationships = sorted(set(validated_relationships))
    if any(not relationship.strip() for relationship in relationships):
        raise ValueError("validated_relationships cannot contain blanks")

    directory.mkdir(parents=True, exist_ok=True)
    artifact_path = directory / "model.joblib"
    joblib.dump(
        {"calibrator": calibrator, "estimator": estimator},
        artifact_path,
        compress=0,
        protocol=4,
    )
    checksum = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    metadata: dict[str, object] = {
        "artifact_sha256": checksum,
        "feature_names": list(FEATURE_NAMES),
        "feature_version": FEATURE_VERSION,
        "metrics": dict(metrics),
        "model_version": model_version,
        "review_gate_passed": bool(review_gate_passed),
        "review_policy": dict(review_policy),
        "seed": seed,
        "thresholds": dict(thresholds),
        "training_dataset_hash": training_dataset_hash,
        "validated_relationships": relationships,
    }
    (directory / "model.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return metadata


def _validate_digest(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _validate_thresholds(thresholds: Mapping[str, float | None]) -> None:
    for name, value in thresholds.items():
        if value is not None and (not math.isfinite(value) or not 0 <= value <= 1):
            raise ValueError(f"{name} threshold must be a finite probability or None")
    auto = thresholds["auto_match"]
    review = thresholds["review"]
    candidate = thresholds["candidate"]
    unresolved = thresholds["unresolved"]
    if candidate != review:
        raise ValueError("candidate and review thresholds must be identical")
    if auto is not None and review is not None and auto < review:
        raise ValueError("auto_match threshold must be at least the review threshold")
    if unresolved is not None and review is None:
        raise ValueError("unresolved threshold requires a review threshold")
    if unresolved is not None and review is not None and unresolved >= review:
        raise ValueError("unresolved threshold must be below the review threshold")
