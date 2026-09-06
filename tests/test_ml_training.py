from datetime import date, timedelta
from decimal import Decimal

import numpy as np

from services.ml.contracts import Candidate, ObservableRecord
from services.ml.training import TrainingExample, grouped_split, train_baselines


def _candidate(component: int, row: int, is_match: bool) -> Candidate:
    amount = Decimal("100.00") + Decimal(component)
    target_amount = amount if is_match else amount + Decimal("17.25")
    record_date = date(2026, 1, 1) + timedelta(days=component)
    reference = f"INV-{component}" if is_match else f"OTHER-{component}-{row}"
    party = f"entity-{component}" if is_match else f"wrong-entity-{component}"
    return Candidate(
        id=f"candidate-{component}-{row}",
        sources=[
            ObservableRecord(
                id=f"source-{component}-{row}",
                record_type="payment",
                amount=amount,
                currency="USD",
                record_date=record_date,
                reference=f"INV-{component}",
                party=f"entity-{component}",
            )
        ],
        targets=[
            ObservableRecord(
                id=f"target-{component}-{row}",
                record_type="settlement",
                amount=target_amount,
                currency="USD",
                record_date=record_date + timedelta(days=0 if is_match else 8),
                reference=reference,
                party=party,
            )
        ],
        graph_score=Decimal("0.95") if is_match else Decimal("0.10"),
    )


def _examples() -> list[TrainingExample]:
    examples = []
    for component in range(12):
        for row, is_match in enumerate((True, False)):
            examples.append(
                TrainingExample(
                    candidate=_candidate(component, row, is_match),
                    is_match=is_match,
                    generator_seed=f"seed-{component}",
                    entity_id=f"entity-{component}",
                    scenario_id=f"scenario-{component}",
                    is_hard_negative=not is_match,
                )
            )
    return examples


def test_grouped_split_has_zero_overlap_for_every_leakage_key() -> None:
    split = grouped_split(_examples(), seed=19)

    for field in ("generator_seed", "entity_id", "scenario_id"):
        train = {getattr(example, field) for example in split.train}
        validation = {getattr(example, field) for example in split.validation}
        test = {getattr(example, field) for example in split.test}
        assert train.isdisjoint(validation)
        assert train.isdisjoint(test)
        assert validation.isdisjoint(test)


def test_training_is_reproducible_and_compares_both_models() -> None:
    first = train_baselines(_examples(), seed=7)
    second = train_baselines(_examples(), seed=7)

    assert set(first.models) == {"logistic_regression", "gradient_boosted_tree"}
    assert first.validation_metrics == second.validation_metrics
    assert first.test_metrics == second.test_metrics
    assert first.best_model_name == second.best_model_name
    assert [item.candidate.id for item in first.split.train] == [
        item.candidate.id for item in second.split.train
    ]
    for name in first.models:
        features = np.asarray(
            [[0.0] * 14, [1.0] * 14],
            dtype=float,
        )
        np.testing.assert_allclose(
            first.models[name].predict_proba(features),
            second.models[name].predict_proba(features),
        )


def test_training_returns_metrics_and_evaluates_hard_negatives() -> None:
    result = train_baselines(_examples(), seed=11)

    assert result.best_model_name in result.models
    for metrics_by_model in (result.validation_metrics, result.test_metrics):
        assert set(metrics_by_model) == set(result.models)
        for metrics in metrics_by_model.values():
            assert 0.0 <= metrics.accuracy <= 1.0
            assert 0.0 <= metrics.precision <= 1.0
            assert 0.0 <= metrics.recall <= 1.0
            assert 0.0 <= metrics.f1 <= 1.0
            assert 0.0 <= metrics.roc_auc <= 1.0
            assert metrics.hard_negative_count > 0
            assert 0 <= metrics.hard_negative_false_positives <= metrics.hard_negative_count
            assert 0.0 <= metrics.hard_negative_false_positive_rate <= 1.0


def test_group_components_link_across_any_holdout_dimension() -> None:
    examples = _examples()
    linked = TrainingExample(
        candidate=_candidate(99, 0, True),
        is_match=True,
        generator_seed=examples[0].generator_seed,
        entity_id="entity-linked",
        scenario_id="scenario-linked",
    )
    examples.append(linked)

    split = grouped_split(examples, seed=3)
    partitions = (split.train, split.validation, split.test)
    assert any(examples[0] in partition and linked in partition for partition in partitions)
