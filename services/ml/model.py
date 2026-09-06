"""Trusted-artifact loading and review-only inference."""

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np

from .contracts import Candidate
from .features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    currency_valid,
    feature_vector,
    review_eligible,
)
from .selection import REVIEW_POLICY, review_mask


def load_model(directory: Path):
    metadata = json.loads((directory / "model.json").read_text())
    if metadata["feature_version"] != FEATURE_VERSION or metadata["feature_names"] != list(
        FEATURE_NAMES
    ):
        raise ValueError("Incompatible feature contract")
    path = directory / "model.joblib"
    if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["artifact_sha256"]:
        raise ValueError("Model artifact checksum mismatch")
    return joblib.load(path), metadata


def _probabilities(model, features):
    raw = model["estimator"].predict_proba(features)[:, 1]
    clipped = np.clip(raw, 1e-8, 1 - 1e-8)
    logits = np.log(clipped / (1 - clipped)).reshape(-1, 1)
    return model["calibrator"].predict_proba(logits)[:, 1]


def rank_candidates(directory: Path, candidates: list[Candidate]) -> list[dict]:
    """Rank exactly one caller-supplied complete batch; never authorize an action."""
    if not candidates:
        return []
    if len({candidate.id for candidate in candidates}) != len(candidates):
        raise ValueError("Duplicate candidate IDs")
    model, metadata = load_model(directory)
    scores = _probabilities(model, [feature_vector(candidate) for candidate in candidates])
    threshold = metadata.get("thresholds", {}).get("review")
    selected = review_mask(candidates, scores, threshold)
    policy_valid = metadata.get("review_policy") == REVIEW_POLICY
    output = []
    for candidate, score, chosen in zip(candidates, scores, selected, strict=True):
        relationship = (
            "+".join(sorted(record.record_type for record in candidate.sources))
            + "->"
            + "+".join(sorted(record.record_type for record in candidate.targets))
        )
        supported = relationship in metadata.get("validated_relationships", [])
        review = bool(
            chosen and supported and metadata.get("review_gate_passed", False) and policy_valid
        )
        if not currency_valid(candidate):
            reason = "CURRENCY_MISMATCH"
        elif not review_eligible(candidate):
            reason = "PARTY_CONFLICT"
        elif not metadata.get("review_gate_passed", False):
            reason = "MODEL_NOT_VALIDATED"
        elif not supported:
            reason = "OUT_OF_DISTRIBUTION_RELATIONSHIP"
        elif not policy_valid:
            reason = "INCOMPATIBLE_REVIEW_POLICY"
        elif review:
            reason = "REVIEW_ONLY_MODEL"
        elif threshold is not None and score >= threshold:
            reason = "AMBIGUOUS_RECORD_MATCH"
        else:
            reason = "BELOW_REVIEW_THRESHOLD"
        output.append(
            {
                "candidate_id": candidate.id,
                "match_probability": float(score),
                "suggestion": "REVIEW" if review else "UNRESOLVED",
                "automatic_action_eligible": False,
                "reason": reason,
                "feature_version": FEATURE_VERSION,
                "model_version": metadata["model_version"],
            }
        )
    return sorted(output, key=lambda row: (-row["match_probability"], row["candidate_id"]))
