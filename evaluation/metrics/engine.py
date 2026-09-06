"""Deterministic metric engine for Phase 6 evaluation harness."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal

from evaluation.contracts import (
    CasePrediction,
    ClassificationMetrics,
    CostMetrics,
    RiskMetrics,
)

ZERO = Decimal(0)
ONE = Decimal(1)


def _ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    if denominator == 0:
        return ZERO
    return Decimal(numerator) / Decimal(denominator)


def _mean(total: Decimal | int, count: int) -> Decimal:
    if count == 0:
        return ZERO
    return Decimal(total) / Decimal(count)


def classification_metrics(
    *,
    true_positives: int,
    false_positives: int,
    true_negatives: int,
    false_negatives: int,
) -> ClassificationMetrics:
    """Compute precision, recall, and F1 from confusion counts."""
    for name, value in (
        ("true_positives", true_positives),
        ("false_positives", false_positives),
        ("true_negatives", true_negatives),
        ("false_negatives", false_negatives),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    precision = _ratio(true_positives, true_positives + false_positives)
    recall = _ratio(true_positives, true_positives + false_negatives)
    if precision == ZERO and recall == ZERO:
        f1 = ZERO
    else:
        f1 = (2 * precision * recall) / (precision + recall)
    return ClassificationMetrics(
        precision=precision,
        recall=recall,
        f1=f1,
        true_positives=true_positives,
        false_positives=false_positives,
        true_negatives=true_negatives,
        false_negatives=false_negatives,
    )


def label_match_metrics(
    expected_labels: Sequence[str],
    predicted_labels: Sequence[str | None],
) -> ClassificationMetrics:
    """Treat exact label equality as the positive class for matching benchmarks."""
    if len(expected_labels) != len(predicted_labels):
        raise ValueError("expected and predicted label sequences must have equal length")
    tp = fp = tn = fn = 0
    for expected, predicted in zip(expected_labels, predicted_labels, strict=True):
        correct = predicted is not None and predicted == expected
        # Matching benchmark: a correct label is a TP; incorrect/missing is FN.
        # When no prediction is required for negatives, callers should use binary_detection_metrics.
        if correct:
            tp += 1
        else:
            fn += 1
            if predicted is not None and predicted != expected:
                fp += 1
    return classification_metrics(
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
    )


def binary_detection_metrics(
    expected_positive: Sequence[bool],
    predicted_positive: Sequence[bool],
) -> ClassificationMetrics:
    if len(expected_positive) != len(predicted_positive):
        raise ValueError("expected and predicted sequences must have equal length")
    tp = fp = tn = fn = 0
    for expected, predicted in zip(expected_positive, predicted_positive, strict=True):
        if expected and predicted:
            tp += 1
        elif expected and not predicted:
            fn += 1
        elif not expected and predicted:
            fp += 1
        else:
            tn += 1
    return classification_metrics(
        true_positives=tp,
        false_positives=fp,
        true_negatives=tn,
        false_negatives=fn,
    )


def accuracy(correct: int, total: int) -> Decimal:
    if correct < 0 or total < 0:
        raise ValueError("correct and total must be non-negative")
    return _ratio(correct, total)


def set_precision_recall(
    expected: Iterable[str],
    predicted: Iterable[str],
) -> tuple[Decimal, Decimal]:
    expected_set = set(expected)
    predicted_set = set(predicted)
    if not expected_set and not predicted_set:
        return ONE, ONE
    overlap = len(expected_set & predicted_set)
    return _ratio(overlap, len(predicted_set)), _ratio(overlap, len(expected_set))


def mean_set_precision_recall(
    pairs: Sequence[tuple[Sequence[str], Sequence[str]]],
) -> tuple[Decimal, Decimal]:
    if not pairs:
        return ZERO, ZERO
    precision_total = ZERO
    recall_total = ZERO
    for expected, predicted in pairs:
        precision, recall = set_precision_recall(expected, predicted)
        precision_total += precision
        recall_total += recall
    count = Decimal(len(pairs))
    return precision_total / count, recall_total / count


def risk_metrics(
    *,
    hard_negative_count: int,
    hard_negative_false_positives: int,
    auto_resolved_count: int,
    case_count: int,
    false_positive_amounts: Sequence[Decimal],
    false_negative_amounts: Sequence[Decimal],
    correctly_reconciled_amounts: Sequence[Decimal],
) -> RiskMetrics:
    if hard_negative_count < 0 or hard_negative_false_positives < 0:
        raise ValueError("hard-negative counts must be non-negative")
    if hard_negative_false_positives > hard_negative_count:
        raise ValueError("hard-negative false positives cannot exceed hard-negative count")
    for amount in (
        *false_positive_amounts,
        *false_negative_amounts,
        *correctly_reconciled_amounts,
    ):
        if not amount.is_finite() or amount < 0:
            raise ValueError("financial amounts must be finite and non-negative")
    return RiskMetrics(
        hard_negative_fp_rate=_ratio(hard_negative_false_positives, hard_negative_count),
        automation_rate=_ratio(auto_resolved_count, case_count),
        false_positive_financial_exposure=sum(false_positive_amounts, ZERO),
        false_negative_financial_exposure=sum(false_negative_amounts, ZERO),
        amount_correctly_reconciled=sum(correctly_reconciled_amounts, ZERO),
    )


def cost_metrics(predictions: Sequence[CasePrediction]) -> CostMetrics:
    if not predictions:
        return CostMetrics(
            latency_ms_total=ZERO,
            latency_ms_mean=ZERO,
            llm_tokens_total=0,
            llm_tokens_mean=ZERO,
            estimated_cost_total=ZERO,
            estimated_cost_mean=ZERO,
        )
    latency_total = sum((item.latency_ms for item in predictions), ZERO)
    tokens_total = sum(item.llm_tokens for item in predictions)
    cost_total = sum((item.estimated_cost for item in predictions), ZERO)
    count = len(predictions)
    return CostMetrics(
        latency_ms_total=latency_total,
        latency_ms_mean=_mean(latency_total, count),
        llm_tokens_total=tokens_total,
        llm_tokens_mean=_mean(tokens_total, count),
        estimated_cost_total=cost_total,
        estimated_cost_mean=_mean(cost_total, count),
    )


def decimal_to_json(value: Decimal | int | str | None) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    return value
