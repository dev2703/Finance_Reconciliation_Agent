"""Deterministic baseline training with leakage-safe grouped holdouts.

The local input protocol deliberately avoids shared schema changes.  Dataset adapters
provide :class:`TrainingExample` values whose candidate uses the existing Phase 5
service contract and whose grouping fields identify the generated world, business
entity, and scenario.  Examples connected through *any* grouping field remain in the
same split.

Money is retained as ``Decimal`` by ``Candidate`` and the feature builder while
differences and ratios are constructed.  Conversion to float occurs only at the
scikit-learn model boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .contracts import Candidate
from .features import feature_vector


@dataclass(frozen=True)
class TrainingExample:
    """One labelled candidate plus all identities that must be held out together."""

    candidate: Candidate
    is_match: bool
    generator_seed: str
    entity_id: str
    scenario_id: str
    is_hard_negative: bool = False

    def __post_init__(self) -> None:
        if not self.generator_seed or not self.entity_id or not self.scenario_id:
            raise ValueError("Every training example requires seed, entity, and scenario groups")
        if self.is_hard_negative and self.is_match:
            raise ValueError("A hard negative cannot be labelled as a match")


@dataclass(frozen=True)
class GroupedSplit:
    train: tuple[TrainingExample, ...]
    validation: tuple[TrainingExample, ...]
    test: tuple[TrainingExample, ...]


@dataclass(frozen=True)
class ModelMetrics:
    accuracy: float
    precision: float
    recall: float
    f1: float
    roc_auc: float
    hard_negative_count: int
    hard_negative_false_positives: int
    hard_negative_false_positive_rate: float


@dataclass(frozen=True)
class BaselineResult:
    split: GroupedSplit
    models: dict[str, object]
    validation_metrics: dict[str, ModelMetrics]
    test_metrics: dict[str, ModelMetrics]
    best_model_name: str


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def _connected_groups(examples: list[TrainingExample]) -> list[list[TrainingExample]]:
    groups = _DisjointSet(len(examples))
    owners: dict[tuple[str, str], int] = {}
    for index, example in enumerate(examples):
        identities = (
            ("seed", example.generator_seed),
            ("entity", example.entity_id),
            ("scenario", example.scenario_id),
        )
        for identity in identities:
            previous = owners.setdefault(identity, index)
            groups.union(index, previous)

    components: dict[int, list[TrainingExample]] = {}
    for index, example in enumerate(examples):
        components.setdefault(groups.find(index), []).append(example)
    return list(components.values())


def grouped_split(
    examples: list[TrainingExample],
    *,
    seed: int = 42,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> GroupedSplit:
    """Split connected group components, preventing overlap on every group dimension."""
    if not examples:
        raise ValueError("Training examples cannot be empty")
    if len({example.candidate.id for example in examples}) != len(examples):
        raise ValueError("Candidate IDs must be unique")
    if not 0 < validation_fraction < 1 or not 0 < test_fraction < 1:
        raise ValueError("Validation and test fractions must be between zero and one")
    if validation_fraction + test_fraction >= 1:
        raise ValueError("Validation and test fractions must leave a training split")

    components = _connected_groups(examples)
    if len(components) < 3:
        raise ValueError("At least three disconnected group components are required")
    Random(seed).shuffle(components)

    total = len(examples)
    validation_target = max(1, round(total * validation_fraction))
    test_target = max(1, round(total * test_fraction))
    validation: list[TrainingExample] = []
    test: list[TrainingExample] = []
    train: list[TrainingExample] = []
    for component in components:
        if len(validation) < validation_target:
            validation.extend(component)
        elif len(test) < test_target:
            test.extend(component)
        else:
            train.extend(component)

    split = GroupedSplit(tuple(train), tuple(validation), tuple(test))
    if not all((split.train, split.validation, split.test)):
        raise ValueError("Grouped components could not produce three non-empty splits")
    _validate_no_group_overlap(split)
    return split


def _validate_no_group_overlap(split: GroupedSplit) -> None:
    for field in ("generator_seed", "entity_id", "scenario_id"):
        values = [
            {getattr(example, field) for example in partition}
            for partition in (split.train, split.validation, split.test)
        ]
        if values[0] & values[1] or values[0] & values[2] or values[1] & values[2]:
            raise AssertionError(f"Grouped split leaked {field}")


def _matrix(examples: tuple[TrainingExample, ...]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([feature_vector(example.candidate) for example in examples], dtype=float),
        np.asarray([int(example.is_match) for example in examples], dtype=int),
    )


def _metrics(model: object, examples: tuple[TrainingExample, ...]) -> ModelMetrics:
    features, labels = _matrix(examples)
    predictions = model.predict(features)
    probabilities = model.predict_proba(features)[:, 1]
    hard_negative = np.asarray([example.is_hard_negative for example in examples], dtype=bool)
    hard_negative_count = int(hard_negative.sum())
    hard_negative_false_positives = int(predictions[hard_negative].sum())
    return ModelMetrics(
        accuracy=float(accuracy_score(labels, predictions)),
        precision=float(precision_score(labels, predictions, zero_division=0)),
        recall=float(recall_score(labels, predictions, zero_division=0)),
        f1=float(f1_score(labels, predictions, zero_division=0)),
        roc_auc=float(roc_auc_score(labels, probabilities)) if len(set(labels)) == 2 else 0.0,
        hard_negative_count=hard_negative_count,
        hard_negative_false_positives=hard_negative_false_positives,
        hard_negative_false_positive_rate=(
            hard_negative_false_positives / hard_negative_count if hard_negative_count else 0.0
        ),
    )


def train_baselines(examples: list[TrainingExample], *, seed: int = 42) -> BaselineResult:
    """Fit and compare deterministic logistic and gradient-boosted baselines."""
    split = grouped_split(examples, seed=seed)
    train_features, train_labels = _matrix(split.train)
    if len(set(train_labels)) != 2:
        raise ValueError("Training split must contain positive and negative examples")
    for name, partition in (("validation", split.validation), ("test", split.test)):
        if len({example.is_match for example in partition}) != 2:
            raise ValueError(f"{name.capitalize()} split must contain both classes")

    models: dict[str, object] = {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(random_state=seed, max_iter=1_000),
        ),
        "gradient_boosted_tree": HistGradientBoostingClassifier(
            random_state=seed,
            max_iter=100,
            max_leaf_nodes=15,
            min_samples_leaf=2,
        ),
    }
    validation_metrics: dict[str, ModelMetrics] = {}
    test_metrics: dict[str, ModelMetrics] = {}
    for name, model in models.items():
        model.fit(train_features, train_labels)
        validation_metrics[name] = _metrics(model, split.validation)
        test_metrics[name] = _metrics(model, split.test)

    best_model_name = max(
        models,
        key=lambda name: (
            validation_metrics[name].f1,
            validation_metrics[name].roc_auc,
            name,
        ),
    )
    return BaselineResult(split, models, validation_metrics, test_metrics, best_model_name)
