"""Baseline vs system comparison helpers."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from evaluation.contracts import BenchmarkComparison, SuiteMetrics, SystemRunResult
from evaluation.metrics.engine import decimal_to_json


def _suite_snapshot(metrics: SuiteMetrics) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "suite": metrics.suite,
        "case_count": metrics.case_count,
        "precision": decimal_to_json(metrics.classification.precision),
        "recall": decimal_to_json(metrics.classification.recall),
        "f1": decimal_to_json(metrics.classification.f1),
        "root_cause_accuracy": decimal_to_json(metrics.root_cause_accuracy),
        "evidence_precision": decimal_to_json(metrics.evidence_precision),
        "evidence_recall": decimal_to_json(metrics.evidence_recall),
        "resolution_accuracy": decimal_to_json(metrics.resolution_accuracy),
    }
    if metrics.risk is not None:
        snapshot.update(
            {
                "hard_negative_fp_rate": decimal_to_json(metrics.risk.hard_negative_fp_rate),
                "automation_rate": decimal_to_json(metrics.risk.automation_rate),
                "false_positive_financial_exposure": decimal_to_json(
                    metrics.risk.false_positive_financial_exposure
                ),
                "false_negative_financial_exposure": decimal_to_json(
                    metrics.risk.false_negative_financial_exposure
                ),
                "amount_correctly_reconciled": decimal_to_json(
                    metrics.risk.amount_correctly_reconciled
                ),
            }
        )
    if metrics.cost is not None:
        snapshot.update(
            {
                "latency_ms_mean": decimal_to_json(metrics.cost.latency_ms_mean),
                "llm_tokens_total": metrics.cost.llm_tokens_total,
                "estimated_cost_total": decimal_to_json(metrics.cost.estimated_cost_total),
            }
        )
    snapshot["extras"] = dict(metrics.extras)
    return snapshot


def _delta(baseline: str | int | None, system: str | int | None) -> str | int | None:
    if baseline is None or system is None:
        return None
    if isinstance(baseline, int) and isinstance(system, int):
        return system - baseline
    try:
        return format(Decimal(str(system)) - Decimal(str(baseline)), "f")
    except Exception:
        return None


def compare_systems(baseline: SystemRunResult, system: SystemRunResult) -> BenchmarkComparison:
    baseline_map = {item.suite: _suite_snapshot(item) for item in baseline.suites}
    system_map = {item.suite: _suite_snapshot(item) for item in system.suites}
    shared = sorted(set(baseline_map) & set(system_map))
    deltas: dict[str, Any] = {}
    for suite in shared:
        left = baseline_map[suite]
        right = system_map[suite]
        suite_delta = {
            key: _delta(left.get(key), right.get(key))
            for key in (
                "precision",
                "recall",
                "f1",
                "root_cause_accuracy",
                "evidence_precision",
                "evidence_recall",
                "resolution_accuracy",
                "hard_negative_fp_rate",
                "automation_rate",
                "false_positive_financial_exposure",
                "false_negative_financial_exposure",
                "amount_correctly_reconciled",
                "latency_ms_mean",
                "llm_tokens_total",
                "estimated_cost_total",
            )
        }
        deltas[suite] = suite_delta
    return BenchmarkComparison(baseline=baseline, system=system, deltas=deltas)


def comparison_to_dict(comparison: BenchmarkComparison) -> Mapping[str, Any]:
    return {
        "baseline": {
            "system_name": comparison.baseline.system_name,
            "suites": [_suite_snapshot(item) for item in comparison.baseline.suites],
        },
        "system": {
            "system_name": comparison.system.system_name,
            "suites": [_suite_snapshot(item) for item in comparison.system.suites],
        },
        "deltas": dict(comparison.deltas),
    }
