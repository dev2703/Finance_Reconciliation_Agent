import hashlib
import json
from datetime import date
from decimal import Decimal
from uuid import uuid4

import joblib
import numpy as np
import pytest

from packages.contracts import FinancialRecord
from services.ml.contracts import Candidate, ObservableRecord
from services.ml.features import FEATURE_NAMES, feature_vector
from services.ml.selection import review_mask
from services.ml.workflow import MLReviewWorkflow, ReviewDecision


class FixedEstimator:
    def predict_proba(self, features):
        probabilities = np.array([0.99 if row[0] == 0 else 0.10 for row in features])
        return np.column_stack((1 - probabilities, probabilities))


class LogisticPassthroughCalibrator:
    def predict_proba(self, logits):
        probabilities = 1 / (1 + np.exp(-logits[:, 0]))
        return np.column_stack((1 - probabilities, probabilities))


def record(amount: str, *, external_id: str, day: int = 10) -> FinancialRecord:
    return FinancialRecord(
        id=uuid4(),
        external_id=external_id,
        amount=Decimal(amount),
        currency="USD",
        record_date=date(2026, 8, day),
        description="Acme settlement",
    )


def ranked_rows(candidates: list[Candidate], scores: dict[str, float]) -> list[dict]:
    selected = review_mask(candidates, [scores[candidate.id] for candidate in candidates], 0.95)
    return [
        {
            "candidate_id": candidate.id,
            "match_probability": scores[candidate.id],
            "suggestion": "REVIEW" if chosen else "UNRESOLVED",
            "automatic_action_eligible": False,
            "reason": "REVIEW_ONLY_MODEL" if chosen else "AMBIGUOUS_RECORD_MATCH",
            "model_version": "test-v1",
        }
        for candidate, chosen in zip(candidates, selected, strict=True)
    ]


def test_complete_candidate_batch_flows_from_graph_to_review_and_audited_decision():
    source = record("100.00", external_id="source")
    best = record("100.00", external_id="best")
    competitor = record("101.00", external_id="competitor")
    observed_batches: list[list[Candidate]] = []

    def ranker(candidates: list[Candidate]) -> list[dict]:
        observed_batches.append(candidates)
        scores = {
            candidate.id: (0.99 if candidate.targets[0].id == str(best.id) else 0.80)
            for candidate in candidates
        }
        return ranked_rows(candidates, scores)

    workflow = MLReviewWorkflow(ranker=ranker)
    outcome = workflow.suggest(
        {"payment": [source], "settlement": [best, competitor]},
        source_type="payment",
        target_type="settlement",
    )

    assert len(observed_batches) == 1
    assert {candidate.targets[0].id for candidate in observed_batches[0]} == {
        str(best.id),
        str(competitor.id),
    }
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0].candidate.targets[0].id == str(best.id)
    assert len(workflow.audit_events) == 1
    assert workflow.audit_events[0].event_type == "ML_REVIEW_PROPOSAL_CREATED"

    decided = workflow.decide(
        outcome.proposals[0].id,
        ReviewDecision.APPROVE,
        actor="reviewer@example.test",
        reason="Evidence checked",
    )
    assert decided.decision is ReviewDecision.APPROVE
    assert len(workflow.audit_events) == 2
    assert workflow.audit_events[1].details["accounting_state_mutated"] is False
    with pytest.raises(ValueError, match="already been decided"):
        workflow.decide(
            decided.id,
            ReviewDecision.REJECT,
            actor="reviewer@example.test",
            reason="Second decision",
        )


def test_ambiguous_and_insufficient_candidate_sets_stay_unresolved():
    source = record("100.00", external_id="source")
    first = record("100.00", external_id="first")
    second = record("100.00", external_id="second")

    ambiguous = MLReviewWorkflow(
        ranker=lambda candidates: ranked_rows(
            candidates, {candidates[0].id: 0.98, candidates[1].id: 0.97}
        )
    ).suggest(
        {"payment": [source], "settlement": [first, second]},
        source_type="payment",
        target_type="settlement",
    )
    assert not ambiguous.proposals
    assert {row.reason for row in ambiguous.unresolved} == {"AMBIGUOUS_RECORD_MATCH"}

    insufficient = MLReviewWorkflow(
        ranker=lambda candidates: ranked_rows(candidates, {candidates[0].id: 0.99})
    ).suggest(
        {"payment": [source], "settlement": [first]},
        source_type="payment",
        target_type="settlement",
    )
    assert not insufficient.proposals
    assert insufficient.unresolved[0].reason == "INSUFFICIENT_CANDIDATE_SET"

    no_candidates = MLReviewWorkflow(ranker=lambda candidates: []).suggest(
        {"payment": [source], "settlement": []},
        source_type="payment",
        target_type="settlement",
    )
    assert not no_candidates.proposals
    assert no_candidates.unresolved[0].reason == "NO_CANDIDATES"


def test_records_without_graph_candidates_are_explicitly_unresolved():
    covered = record("100.00", external_id="covered")
    orphan = record("100.00", external_id="orphan", day=1)
    targets = [
        record("100.00", external_id="first", day=10),
        record("100.00", external_id="second", day=10),
    ]
    outcome = MLReviewWorkflow(
        ranker=lambda candidates: ranked_rows(
            candidates, {candidates[0].id: 0.99, candidates[1].id: 0.80}
        )
    ).suggest(
        {"payment": [covered, orphan], "settlement": targets},
        source_type="payment",
        target_type="settlement",
    )
    assert any(
        row.candidate_id == f"payment:{orphan.id}" and row.reason == "NO_CANDIDATES"
        for row in outcome.unresolved
    )


@pytest.mark.parametrize(
    ("sources", "targets"),
    [
        (
            [record("100.00", external_id="s")],
            [record("40.00", external_id="a"), record("60.00", external_id="b")],
        ),
        (
            [record("40.00", external_id="a"), record("60.00", external_id="b")],
            [record("100.00", external_id="t")],
        ),
    ],
)
def test_one_to_many_and_many_to_one_allocations_are_explicitly_unresolved(sources, targets):
    workflow = MLReviewWorkflow(
        ranker=lambda candidates: ranked_rows(
            candidates, {candidate.id: 0.99 for candidate in candidates}
        )
    )
    outcome = workflow.suggest(
        {"payment": sources, "settlement": targets},
        source_type="payment",
        target_type="settlement",
    )
    assert not outcome.proposals
    assert outcome.unresolved
    assert {row.reason for row in outcome.unresolved} == {"UNSUPPORTED_ALLOCATION"}
    assert not workflow.audit_events


@pytest.mark.parametrize(
    "model_reason", ["MODEL_NOT_VALIDATED", "OUT_OF_DISTRIBUTION_RELATIONSHIP"]
)
def test_partial_payment_and_uncalibrated_or_ood_results_never_propose_review(model_reason):
    source = record("100.00", external_id="source")
    partial = record("70.00", external_id="partial")
    other = record("80.00", external_id="other")
    partial_outcome = MLReviewWorkflow(
        ranker=lambda candidates: ranked_rows(
            candidates, {candidate.id: 0.99 for candidate in candidates}
        )
    ).suggest(
        {"payment": [source], "settlement": [partial, other]},
        source_type="payment",
        target_type="settlement",
    )
    assert not partial_outcome.proposals
    assert {row.reason for row in partial_outcome.unresolved} == {"UNSUPPORTED_PARTIAL_PAYMENT"}

    def fail_closed(candidates: list[Candidate]) -> list[dict]:
        return [
            {
                "candidate_id": candidate.id,
                "match_probability": 0.999,
                "suggestion": "UNRESOLVED",
                "automatic_action_eligible": False,
                "reason": model_reason,
                "model_version": "uncalibrated",
            }
            for candidate in candidates
        ]

    uncalibrated = MLReviewWorkflow(ranker=fail_closed).suggest(
        {
            "payment": [source],
            "settlement": [record("100.00", external_id="x"), record("100.00", external_id="y")],
        },
        source_type="payment",
        target_type="settlement",
    )
    assert not uncalibrated.proposals
    assert {row.reason for row in uncalibrated.unresolved} == {model_reason}


def test_money_features_preserve_decimal_cents_and_ranker_cannot_enable_auto_action():
    source = ObservableRecord(
        id="source",
        record_type="payment",
        amount=Decimal("10000000000000000.01"),
        currency="USD",
        record_date=date(2026, 8, 10),
    )
    target = source.model_copy(
        update={
            "id": "target",
            "record_type": "settlement",
            "amount": Decimal("10000000000000000.02"),
        }
    )
    candidate = Candidate(id="precision", sources=[source], targets=[target])
    values = dict(zip(FEATURE_NAMES, feature_vector(candidate), strict=True))
    assert values["absolute_delta"] == 0.01

    left = record("100.00", external_id="left")
    targets = [record("100.00", external_id="one"), record("100.00", external_id="two")]

    def unsafe(candidates: list[Candidate]) -> list[dict]:
        rows = ranked_rows(candidates, {candidates[0].id: 0.99, candidates[1].id: 0.80})
        rows[0]["automatic_action_eligible"] = True
        return rows

    with pytest.raises(ValueError, match="review-only contract"):
        MLReviewWorkflow(ranker=unsafe).suggest(
            {"payment": [left], "settlement": targets},
            source_type="payment",
            target_type="settlement",
        )


def test_large_decimal_partial_payment_cannot_round_into_review():
    source = record("1234567890123456789012345678.01", external_id="source")
    targets = [
        record("1234567890123456789012345678.02", external_id="near"),
        record("1234567890123456789012345678.03", external_id="other"),
    ]
    outcome = MLReviewWorkflow(
        ranker=lambda candidates: ranked_rows(
            candidates, {candidates[0].id: 0.99, candidates[1].id: 0.80}
        )
    ).suggest(
        {"payment": [source], "settlement": targets},
        source_type="payment",
        target_type="settlement",
    )
    assert not outcome.proposals
    assert {row.reason for row in outcome.unresolved} == {"UNSUPPORTED_PARTIAL_PAYMENT"}


def test_real_artifact_loading_and_inference_path(tmp_path):
    source = record("100.00", external_id="source")
    targets = [record("100.00", external_id="best"), record("101.00", external_id="other")]
    artifact = tmp_path / "model.joblib"
    joblib.dump(
        {"estimator": FixedEstimator(), "calibrator": LogisticPassthroughCalibrator()}, artifact
    )
    metadata = {
        "artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        "feature_names": list(FEATURE_NAMES),
        "feature_version": "phase5-features-v1",
        "model_version": "integration-test",
        "review_gate_passed": True,
        "review_policy": {"version": "record-competition-v1", "minimum_margin": 0.05},
        "thresholds": {"review": 0.95},
        "validated_relationships": ["payment->settlement"],
    }
    (tmp_path / "model.json").write_text(json.dumps(metadata))
    outcome = MLReviewWorkflow(model_directory=tmp_path).suggest(
        {"payment": [source], "settlement": targets},
        source_type="payment",
        target_type="settlement",
    )
    assert len(outcome.proposals) == 1
    assert outcome.proposals[0].model_version == "integration-test"

    metadata["thresholds"] = {}
    (tmp_path / "model.json").write_text(json.dumps(metadata))
    outcome = MLReviewWorkflow(model_directory=tmp_path).suggest(
        {"payment": [source], "settlement": targets},
        source_type="payment",
        target_type="settlement",
    )
    assert not outcome.proposals
    assert any(row.reason == "MODEL_NOT_CALIBRATED" for row in outcome.unresolved)


@pytest.mark.parametrize("scores", [(0.99, 0.94), (0.85, 0.80), (0.55, 0.50), (0.35, 0.30)])
def test_equal_nominal_margin_is_selected_consistently(scores):
    source = ObservableRecord(
        id="source",
        record_type="payment",
        amount=Decimal(100),
        currency="USD",
        record_date=date(2026, 8, 10),
    )
    candidates = [
        Candidate(
            id=f"candidate-{index}",
            sources=[source],
            targets=[source.model_copy(update={"id": f"target-{index}"})],
        )
        for index in range(2)
    ]
    assert review_mask(candidates, list(scores), 0.30) == [True, False]
