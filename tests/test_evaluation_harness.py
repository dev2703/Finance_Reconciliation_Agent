"""Phase 6 evaluation harness tests."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from evaluation.cli import run_benchmark
from evaluation.contracts import CasePrediction
from evaluation.datasets.finbalance import load_finbalance
from evaluation.metrics import (
    binary_detection_metrics,
    classification_metrics,
    cost_metrics,
    risk_metrics,
    set_precision_recall,
)
from evaluation.runners.compare import compare_systems
from evaluation.runners.finbalance import run_finbalance, score_finbalance
from evaluation.runners.finrca import run_finrca, score_finrca
from evaluation.runners.predictions import PredictionFormatError, load_predictions
from evaluation.runners.reconriver import run_reconriver, score_reconriver
from services.ml.datasets import load_finrca, load_reconriver

FIXTURES = Path(__file__).resolve().parents[1] / "evaluation" / "datasets" / "fixtures"


def test_metric_engine_precision_recall_f1_and_exposure():
    metrics = classification_metrics(
        true_positives=2, false_positives=1, true_negatives=3, false_negatives=1
    )
    assert metrics.precision == Decimal(2) / Decimal(3)
    assert metrics.recall == Decimal(2) / Decimal(3)
    assert metrics.f1 == Decimal(2) / Decimal(3)

    detection = binary_detection_metrics([True, True, False, False], [True, False, True, False])
    assert detection.true_positives == 1
    assert detection.false_negatives == 1
    assert detection.false_positives == 1
    assert detection.true_negatives == 1

    precision, recall = set_precision_recall(["a", "b"], ["b", "c"])
    assert precision == Decimal("0.5")
    assert recall == Decimal("0.5")

    risk = risk_metrics(
        hard_negative_count=2,
        hard_negative_false_positives=1,
        auto_resolved_count=3,
        case_count=4,
        false_positive_amounts=[Decimal("10.00"), Decimal("2.50")],
        false_negative_amounts=[Decimal("7.00")],
        correctly_reconciled_amounts=[Decimal("100.00")],
    )
    assert risk.hard_negative_fp_rate == Decimal("0.5")
    assert risk.automation_rate == Decimal("0.75")
    assert risk.false_positive_financial_exposure == Decimal("12.50")
    assert risk.false_negative_financial_exposure == Decimal("7.00")
    assert risk.amount_correctly_reconciled == Decimal("100.00")

    cost = cost_metrics(
        [
            CasePrediction(
                case_id="1",
                latency_ms=Decimal(10),
                llm_tokens=4,
                estimated_cost=Decimal("0.2"),
            ),
            CasePrediction(
                case_id="2",
                latency_ms=Decimal(30),
                llm_tokens=6,
                estimated_cost=Decimal("0.4"),
            ),
        ]
    )
    assert cost.latency_ms_mean == Decimal(20)
    assert cost.llm_tokens_total == 10
    assert cost.estimated_cost_total == Decimal("0.6")


def test_reconriver_runner_scores_all_four_scenarios():
    metrics, predictions, cases = run_reconriver(
        FIXTURES / "reconriver",
        FIXTURES / "reconriver" / "predictions_system.jsonl",
    )
    assert len(cases) == 5
    assert {case.grouping.scenario for case in cases} == {
        "clean-settlement",
        "mixed-exceptions",
        "month-end-close",
        "failure-recovery",
    }
    assert metrics.classification.f1 == Decimal(1)
    assert metrics.extras["outcome_accuracy"] == "1"
    assert metrics.risk is not None
    assert metrics.risk.false_positive_financial_exposure == Decimal(0)
    assert len(predictions) == 5


def test_finrca_runner_scores_detection_root_cause_evidence_resolution():
    metrics, _, cases = run_finrca(
        FIXTURES / "finrca",
        FIXTURES / "finrca" / "predictions_system.jsonl",
    )
    assert len(cases) == 2
    assert metrics.classification.f1 == Decimal(1)
    assert metrics.root_cause_accuracy == Decimal(1)
    assert metrics.evidence_precision == Decimal(1)
    assert metrics.evidence_recall == Decimal(1)
    assert metrics.resolution_accuracy == Decimal(1)
    assert metrics.risk is not None
    assert metrics.risk.hard_negative_fp_rate == Decimal(0)


def test_finbalance_runner_scores_journals_and_contradictions():
    cases = load_finbalance(FIXTURES / "finbalance")
    assert len(cases) == 2
    assert cases[0].expected_journal_entries[0]["debit"] == Decimal("100.00")

    metrics, _, _ = run_finbalance(
        FIXTURES / "finbalance",
        FIXTURES / "finbalance" / "predictions_system.jsonl",
    )
    assert metrics.resolution_accuracy == Decimal(1)
    assert metrics.extras["field_accuracy"] == "1"
    assert metrics.evidence_precision == Decimal(1)
    assert metrics.evidence_recall == Decimal(1)
    assert metrics.risk is not None
    assert metrics.risk.amount_correctly_reconciled == Decimal("150.00")


def test_cli_writes_json_and_markdown_with_baseline_comparison(tmp_path):
    json_path, markdown_path = run_benchmark(
        fixtures_root=FIXTURES,
        output_dir=tmp_path / "out",
        suites=("reconriver", "finrca", "finbalance"),
    )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload["comparison"]["deltas"]) == {"reconriver", "finrca", "finbalance"}
    assert payload["comparison"]["baseline"]["system_name"] == "deterministic-only"
    assert payload["comparison"]["system"]["system_name"] == "system"
    # System beats baseline F1 on ReconRiver fixtures.
    system_f1 = Decimal(payload["comparison"]["system"]["suites"][0]["f1"])
    baseline_f1 = Decimal(payload["comparison"]["baseline"]["suites"][0]["f1"])
    assert system_f1 > baseline_f1
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "# Evaluation benchmark report" in markdown
    assert "### Delta (system - baseline)" in markdown


def test_cli_demo_mode_seeds_pack_and_writes_reports(tmp_path):
    from evaluation.cli import main

    demo_dir = tmp_path / "demo"
    output_dir = tmp_path / "reports"
    assert (
        main(
            [
                "--demo-dir",
                str(demo_dir),
                "--output",
                str(output_dir),
                "--seed",
                "20260906",
            ]
        )
        == 0
    )
    assert (demo_dir / "cases.jsonl").exists()
    report = json.loads((output_dir / "benchmark.json").read_text(encoding="utf-8"))
    assert report["system"]["suites"][0]["case_count"] == 40
    assert "| System |" in (output_dir / "benchmark.md").read_text(encoding="utf-8")


def test_predictions_reject_blank_and_duplicate_rows(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"case_id":"A","predicted_label":"X"}\n\n', encoding="utf-8")
    with pytest.raises(PredictionFormatError, match="blank JSONL"):
        load_predictions(path)

    path.write_text(
        '{"case_id":"A","predicted_label":"X"}\n{"case_id":"A","predicted_label":"Y"}\n',
        encoding="utf-8",
    )
    with pytest.raises(PredictionFormatError, match="duplicate case_id"):
        load_predictions(path)


def test_score_helpers_require_complete_prediction_coverage():
    cases = load_reconriver(FIXTURES / "reconriver" / "clean-settlement")
    with pytest.raises(PredictionFormatError, match="missing predictions"):
        score_reconriver(cases, [])

    finrca_cases = load_finrca(FIXTURES / "finrca")
    with pytest.raises(PredictionFormatError, match="missing predictions"):
        score_finrca(finrca_cases, [])

    finbalance_cases = load_finbalance(FIXTURES / "finbalance")
    with pytest.raises(PredictionFormatError, match="missing predictions"):
        score_finbalance(finbalance_cases, [])


def test_compare_systems_emits_numeric_deltas():
    from evaluation.contracts import SystemRunResult

    baseline_metrics, _, _ = run_reconriver(
        FIXTURES / "reconriver",
        FIXTURES / "reconriver" / "predictions_baseline.jsonl",
    )
    system_metrics, _, _ = run_reconriver(
        FIXTURES / "reconriver",
        FIXTURES / "reconriver" / "predictions_system.jsonl",
    )
    comparison = compare_systems(
        SystemRunResult("baseline", (baseline_metrics,)),
        SystemRunResult("system", (system_metrics,)),
    )
    assert comparison.deltas["reconriver"]["f1"] is not None
    assert Decimal(comparison.deltas["reconriver"]["f1"]) > 0
