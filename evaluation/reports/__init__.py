"""JSON and markdown report writers for Phase 6 benchmarks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evaluation.contracts import BenchmarkComparison, SuiteMetrics
from evaluation.metrics.engine import decimal_to_json
from evaluation.runners.compare import comparison_to_dict


def suite_to_dict(metrics: SuiteMetrics) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "suite": metrics.suite,
        "case_count": metrics.case_count,
        "classification": {
            "precision": decimal_to_json(metrics.classification.precision),
            "recall": decimal_to_json(metrics.classification.recall),
            "f1": decimal_to_json(metrics.classification.f1),
            "true_positives": metrics.classification.true_positives,
            "false_positives": metrics.classification.false_positives,
            "true_negatives": metrics.classification.true_negatives,
            "false_negatives": metrics.classification.false_negatives,
        },
        "root_cause_accuracy": decimal_to_json(metrics.root_cause_accuracy),
        "evidence_precision": decimal_to_json(metrics.evidence_precision),
        "evidence_recall": decimal_to_json(metrics.evidence_recall),
        "resolution_accuracy": decimal_to_json(metrics.resolution_accuracy),
        "extras": dict(metrics.extras),
    }
    if metrics.risk is not None:
        payload["risk"] = {
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
    if metrics.cost is not None:
        payload["cost"] = {
            "latency_ms_total": decimal_to_json(metrics.cost.latency_ms_total),
            "latency_ms_mean": decimal_to_json(metrics.cost.latency_ms_mean),
            "llm_tokens_total": metrics.cost.llm_tokens_total,
            "llm_tokens_mean": decimal_to_json(metrics.cost.llm_tokens_mean),
            "estimated_cost_total": decimal_to_json(metrics.cost.estimated_cost_total),
            "estimated_cost_mean": decimal_to_json(metrics.cost.estimated_cost_mean),
        }
    return payload


def write_json_report(path: str | Path, payload: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _metric_line(label: str, value: Any) -> str:
    return f"- **{label}:** `{value}`"


def render_markdown(comparison: BenchmarkComparison) -> str:
    lines = [
        "# Evaluation benchmark report",
        "",
        f"Baseline: `{comparison.baseline.system_name}`",
        f"System: `{comparison.system.system_name}`",
        "",
    ]
    baseline_map = {item.suite: item for item in comparison.baseline.suites}
    system_map = {item.suite: item for item in comparison.system.suites}
    for suite in sorted(set(baseline_map) | set(system_map)):
        lines.append(f"## {suite}")
        lines.append("")
        system_metrics = system_map.get(suite)
        baseline_metrics = baseline_map.get(suite)
        if system_metrics is not None:
            lines.append("### System")
            lines.append(_metric_line("cases", system_metrics.case_count))
            lines.append(_metric_line("precision", system_metrics.classification.precision))
            lines.append(_metric_line("recall", system_metrics.classification.recall))
            lines.append(_metric_line("f1", system_metrics.classification.f1))
            if system_metrics.root_cause_accuracy is not None:
                lines.append(
                    _metric_line("root_cause_accuracy", system_metrics.root_cause_accuracy)
                )
            if system_metrics.evidence_precision is not None:
                lines.append(_metric_line("evidence_precision", system_metrics.evidence_precision))
                lines.append(_metric_line("evidence_recall", system_metrics.evidence_recall))
            if system_metrics.resolution_accuracy is not None:
                lines.append(
                    _metric_line("resolution_accuracy", system_metrics.resolution_accuracy)
                )
            if system_metrics.risk is not None:
                lines.append(
                    _metric_line(
                        "false_positive_financial_exposure",
                        system_metrics.risk.false_positive_financial_exposure,
                    )
                )
                lines.append(
                    _metric_line(
                        "hard_negative_fp_rate",
                        system_metrics.risk.hard_negative_fp_rate,
                    )
                )
            lines.append("")
        if baseline_metrics is not None:
            lines.append("### Baseline")
            lines.append(_metric_line("precision", baseline_metrics.classification.precision))
            lines.append(_metric_line("recall", baseline_metrics.classification.recall))
            lines.append(_metric_line("f1", baseline_metrics.classification.f1))
            lines.append("")
        delta = comparison.deltas.get(suite)
        if delta:
            lines.append("### Delta (system - baseline)")
            for key, value in delta.items():
                if value is not None:
                    lines.append(_metric_line(key, value))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(path: str | Path, comparison: BenchmarkComparison) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(comparison), encoding="utf-8")
    return path


def build_report_payload(comparison: BenchmarkComparison) -> dict[str, Any]:
    return {
        "comparison": comparison_to_dict(comparison),
        "baseline_suites": [suite_to_dict(item) for item in comparison.baseline.suites],
        "system_suites": [suite_to_dict(item) for item in comparison.system.suites],
    }
