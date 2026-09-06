from __future__ import annotations

import json

from evaluation.demo import CASE_COUNTS, build_demo_cases, seed_demo_data
from evaluation.harness import run_demo_benchmark
from services.ml.datasets import load_custom_benchmark


def test_demo_pack_has_required_case_distribution_and_stable_ground_truth():
    cases = build_demo_cases()
    assert len(cases) == sum(CASE_COUNTS.values()) == 40
    observed = {label: 0 for label in CASE_COUNTS}
    for case in cases:
        observed[case["label"]] += 1
        assert case["ground_truth"]["expected_outcome"] == case["label"]
        assert case["ground_truth"]["evidence_ids"]
    assert observed == CASE_COUNTS
    assert build_demo_cases() == cases


def test_one_command_inputs_generate_json_and_markdown_comparison(tmp_path):
    demo_paths = seed_demo_data(tmp_path / "demo")
    cases = load_custom_benchmark(demo_paths["cases"])
    assert len(cases) == 40

    comparison = run_demo_benchmark(tmp_path / "demo", tmp_path / "reports")
    assert comparison.system.suites[0].classification.f1 == 1
    assert comparison.system.suites[0].classification.f1 > (
        comparison.baseline.suites[0].classification.f1
    )
    assert comparison.system.suites[0].risk.false_positive_financial_exposure == 0
    assert comparison.system.suites[0].risk.false_negative_financial_exposure == 0
    report = json.loads((tmp_path / "reports" / "benchmark.json").read_text())
    assert report["system"]["suites"][0]["case_count"] == 40
    assert "| System |" in (tmp_path / "reports" / "benchmark.md").read_text()
