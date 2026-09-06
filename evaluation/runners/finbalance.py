"""FinBalance document/accounting ingestion benchmark runner."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from evaluation.contracts import CasePrediction, SuiteMetrics
from evaluation.datasets.finbalance import FinBalanceCase, load_finbalance
from evaluation.metrics import (
    accuracy,
    binary_detection_metrics,
    cost_metrics,
    mean_set_precision_recall,
    risk_metrics,
)
from evaluation.runners.predictions import load_predictions, require_predictions_for_cases


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (str, int)):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _normalize_journal(entry: Mapping[str, Any]) -> tuple[str, Decimal, Decimal] | None:
    account = entry.get("account")
    debit = _as_decimal(entry.get("debit"))
    credit = _as_decimal(entry.get("credit"))
    if not isinstance(account, str) or not account.strip() or debit is None or credit is None:
        return None
    return account.strip(), debit, credit


def _journal_accuracy(
    expected: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
) -> Decimal:
    expected_set = {
        item for item in (_normalize_journal(entry) for entry in expected) if item is not None
    }
    predicted_set = {
        item for item in (_normalize_journal(entry) for entry in predicted) if item is not None
    }
    if not expected_set:
        return Decimal(1) if not predicted_set else Decimal(0)
    overlap = len(expected_set & predicted_set)
    return Decimal(overlap) / Decimal(len(expected_set))


def _field_accuracy(expected: Mapping[str, Any], predicted: Mapping[str, Any]) -> Decimal:
    if not expected:
        return Decimal(1)
    correct = 0
    for key, value in expected.items():
        predicted_value = predicted.get(key)
        if isinstance(value, Decimal):
            parsed = _as_decimal(predicted_value)
            if parsed == value:
                correct += 1
        elif predicted_value == value:
            correct += 1
    return Decimal(correct) / Decimal(len(expected))


def score_finbalance(
    cases: Sequence[FinBalanceCase],
    predictions: Sequence[CasePrediction],
    *,
    suite: str = "finbalance",
) -> SuiteMetrics:
    indexed = require_predictions_for_cases(predictions, [case.case_id for case in cases])
    ordered = [indexed[case.case_id] for case in cases]

    expected_has_contradiction = [bool(case.contradiction_labels) for case in cases]
    predicted_has_contradiction = [bool(item.contradiction_ids) for item in ordered]
    detection = binary_detection_metrics(expected_has_contradiction, predicted_has_contradiction)

    evidence_pairs = [
        (case.contradiction_labels, prediction.contradiction_ids)
        for case, prediction in zip(cases, ordered, strict=True)
    ]
    contradiction_precision, contradiction_recall = mean_set_precision_recall(evidence_pairs)

    journal_scores: list[Decimal] = []
    field_scores: list[Decimal] = []
    balanced_correct = 0
    auto_resolved = 0
    fp_amounts: list[Decimal] = []
    fn_amounts: list[Decimal] = []
    correct_amounts: list[Decimal] = []

    for case, prediction in zip(cases, ordered, strict=True):
        amount = (
            prediction.amount
            if prediction.amount > 0
            else (max((abs(value) for value in case.amounts), default=Decimal(0)))
        )
        journal_score = _journal_accuracy(case.expected_journal_entries, prediction.journal_entries)
        field_score = _field_accuracy(case.expected_fields, prediction.parsed_fields)
        journal_scores.append(journal_score)
        field_scores.append(field_score)

        predicted_journals = [
            item
            for item in (_normalize_journal(entry) for entry in prediction.journal_entries)
            if item
        ]
        debit_total = sum((item[1] for item in predicted_journals), Decimal(0))
        credit_total = sum((item[2] for item in predicted_journals), Decimal(0))
        if predicted_journals and debit_total == credit_total:
            balanced_correct += 1

        contradiction_ok = set(prediction.contradiction_ids) == set(case.contradiction_labels)
        perfect = journal_score == Decimal(1) and field_score == Decimal(1) and contradiction_ok
        if perfect:
            correct_amounts.append(amount)
        elif case.contradiction_labels and not prediction.contradiction_ids:
            fn_amounts.append(amount)
        elif not case.contradiction_labels and prediction.contradiction_ids:
            fp_amounts.append(amount)
        elif prediction.auto_resolved and not perfect:
            fp_amounts.append(amount)

        if prediction.auto_resolved:
            auto_resolved += 1

    case_count = len(cases)
    mean_journal = (
        sum(journal_scores, Decimal(0)) / Decimal(case_count) if case_count else Decimal(0)
    )
    mean_fields = sum(field_scores, Decimal(0)) / Decimal(case_count) if case_count else Decimal(0)

    return SuiteMetrics(
        suite=suite,
        case_count=case_count,
        classification=detection,
        evidence_precision=contradiction_precision,
        evidence_recall=contradiction_recall,
        resolution_accuracy=mean_journal,
        risk=risk_metrics(
            hard_negative_count=sum(1 for case in cases if not case.contradiction_labels),
            hard_negative_false_positives=sum(
                1
                for case, prediction in zip(cases, ordered, strict=True)
                if not case.contradiction_labels and prediction.contradiction_ids
            ),
            auto_resolved_count=auto_resolved,
            case_count=case_count,
            false_positive_amounts=fp_amounts,
            false_negative_amounts=fn_amounts,
            correctly_reconciled_amounts=correct_amounts,
        ),
        cost=cost_metrics(ordered),
        extras={
            "journal_entry_accuracy": format(mean_journal, "f"),
            "field_accuracy": format(mean_fields, "f"),
            "balanced_journal_rate": format(accuracy(balanced_correct, case_count), "f"),
            "industries": sorted({case.industry for case in cases}),
        },
    )


def run_finbalance(
    root: str | Path,
    predictions_path: str | Path,
    *,
    suite: str = "finbalance",
) -> tuple[SuiteMetrics, tuple[CasePrediction, ...], tuple[FinBalanceCase, ...]]:
    cases = load_finbalance(root)
    predictions = load_predictions(predictions_path)
    metrics = score_finbalance(cases, predictions, suite=suite)
    return metrics, predictions, cases
