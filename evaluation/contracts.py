"""Service-local evaluation contracts for Phase 6 benchmark runners."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class CasePrediction:
    """One system prediction for a ground-truth case.

    Money fields use ``Decimal``. Token/cost telemetry is optional and defaults to zero
    when the evaluated system does not call an LLM.
    """

    case_id: str
    predicted_label: str | None = None
    detected_exception: bool | None = None
    root_cause: str | None = None
    evidence_ids: tuple[str, ...] = ()
    resolution: str | None = None
    auto_resolved: bool = False
    amount: Decimal = Decimal(0)
    latency_ms: Decimal = Decimal(0)
    llm_tokens: int = 0
    estimated_cost: Decimal = Decimal(0)
    journal_entries: tuple[Mapping[str, Any], ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    parsed_fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClassificationMetrics:
    precision: Decimal
    recall: Decimal
    f1: Decimal
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int


@dataclass(frozen=True)
class RiskMetrics:
    hard_negative_fp_rate: Decimal
    automation_rate: Decimal
    false_positive_financial_exposure: Decimal
    false_negative_financial_exposure: Decimal
    amount_correctly_reconciled: Decimal


@dataclass(frozen=True)
class CostMetrics:
    latency_ms_total: Decimal
    latency_ms_mean: Decimal
    llm_tokens_total: int
    llm_tokens_mean: Decimal
    estimated_cost_total: Decimal
    estimated_cost_mean: Decimal


@dataclass(frozen=True)
class SuiteMetrics:
    """Aggregated metrics for one benchmark suite run."""

    suite: str
    case_count: int
    classification: ClassificationMetrics
    root_cause_accuracy: Decimal | None = None
    evidence_precision: Decimal | None = None
    evidence_recall: Decimal | None = None
    resolution_accuracy: Decimal | None = None
    risk: RiskMetrics | None = None
    cost: CostMetrics | None = None
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SystemRunResult:
    """Full result for one named system (baseline or candidate)."""

    system_name: str
    suites: tuple[SuiteMetrics, ...]
    predictions: tuple[CasePrediction, ...] = ()


@dataclass(frozen=True)
class BenchmarkComparison:
    """Baseline vs system comparison used by the Phase 6 exit gate."""

    baseline: SystemRunResult
    system: SystemRunResult
    deltas: Mapping[str, Any]


def prediction_index(predictions: Sequence[CasePrediction]) -> dict[str, CasePrediction]:
    indexed: dict[str, CasePrediction] = {}
    for prediction in predictions:
        if prediction.case_id in indexed:
            raise ValueError(f"duplicate prediction for case_id {prediction.case_id!r}")
        indexed[prediction.case_id] = prediction
    return indexed
