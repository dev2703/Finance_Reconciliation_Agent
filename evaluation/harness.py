"""One-command custom benchmark comparison and report generation."""

from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from evaluation.contracts import BenchmarkComparison, SystemRunResult
from evaluation.runners.finrca import score_finrca
from evaluation.runners.predictions import load_predictions
from services.ml.datasets import load_custom_benchmark


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def compare_custom_benchmark(
    cases_path: str | Path,
    baseline_predictions_path: str | Path,
    system_predictions_path: str | Path,
) -> BenchmarkComparison:
    cases = load_custom_benchmark(cases_path)
    baseline_predictions = load_predictions(baseline_predictions_path)
    system_predictions = load_predictions(system_predictions_path)
    baseline_metrics = score_finrca(cases, baseline_predictions, suite="custom_demo")
    system_metrics = score_finrca(cases, system_predictions, suite="custom_demo")
    baseline = SystemRunResult("baseline", (baseline_metrics,), baseline_predictions)
    system = SystemRunResult("system", (system_metrics,), system_predictions)
    deltas = {
        "precision": system_metrics.classification.precision
        - baseline_metrics.classification.precision,
        "recall": system_metrics.classification.recall
        - baseline_metrics.classification.recall,
        "f1": system_metrics.classification.f1 - baseline_metrics.classification.f1,
        "false_positive_exposure": (
            system_metrics.risk.false_positive_financial_exposure
            - baseline_metrics.risk.false_positive_financial_exposure
        ),
        "false_negative_exposure": (
            system_metrics.risk.false_negative_financial_exposure
            - baseline_metrics.risk.false_negative_financial_exposure
        ),
    }
    return BenchmarkComparison(baseline, system, deltas)


def write_reports(comparison: BenchmarkComparison, output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "benchmark.json"
    markdown_path = output / "benchmark.md"
    json_path.write_text(
        json.dumps(_json_value(asdict(comparison)), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    baseline = comparison.baseline.suites[0]
    system = comparison.system.suites[0]
    markdown_path.write_text(
        "# Benchmark comparison\n\n"
        "| System | Cases | Precision | Recall | F1 | FP exposure | FN exposure |\n"
        "|---|---:|---:|---:|---:|---:|---:|\n"
        f"| Baseline | {baseline.case_count} | {baseline.classification.precision} | "
        f"{baseline.classification.recall} | {baseline.classification.f1} | "
        f"{baseline.risk.false_positive_financial_exposure} | "
        f"{baseline.risk.false_negative_financial_exposure} |\n"
        f"| System | {system.case_count} | {system.classification.precision} | "
        f"{system.classification.recall} | {system.classification.f1} | "
        f"{system.risk.false_positive_financial_exposure} | "
        f"{system.risk.false_negative_financial_exposure} |\n",
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path}


def run_demo_benchmark(demo_dir: str | Path, output_dir: str | Path) -> BenchmarkComparison:
    demo = Path(demo_dir)
    comparison = compare_custom_benchmark(
        demo / "cases.jsonl",
        demo / "baseline_predictions.jsonl",
        demo / "system_predictions.jsonl",
    )
    write_reports(comparison, output_dir)
    return comparison
