"""Phase 6 evaluation CLI: one command runs offline benchmark packs."""

from __future__ import annotations

import argparse
from pathlib import Path

from evaluation.contracts import SystemRunResult
from evaluation.demo import seed_demo_data
from evaluation.harness import run_demo_benchmark
from evaluation.reports import build_report_payload, write_json_report, write_markdown_report
from evaluation.runners.compare import compare_systems
from evaluation.runners.finbalance import run_finbalance
from evaluation.runners.finrca import run_finrca
from evaluation.runners.reconriver import run_reconriver

DEFAULT_FIXTURES = Path(__file__).resolve().parent / "datasets" / "fixtures"


def _suite_paths(fixtures_root: Path) -> dict[str, Path]:
    return {
        "reconriver": fixtures_root / "reconriver",
        "finrca": fixtures_root / "finrca",
        "finbalance": fixtures_root / "finbalance",
    }


def run_benchmark(
    *,
    fixtures_root: Path,
    output_dir: Path,
    suites: tuple[str, ...],
    baseline_name: str = "deterministic-only",
    system_name: str = "system",
) -> tuple[Path, Path]:
    paths = _suite_paths(fixtures_root)
    baseline_suites = []
    system_suites = []
    for suite in suites:
        root = paths[suite]
        baseline_predictions = root / "predictions_baseline.jsonl"
        system_predictions = root / "predictions_system.jsonl"
        if suite == "reconriver":
            baseline_metrics, _, _ = run_reconriver(root, baseline_predictions)
            system_metrics, _, _ = run_reconriver(root, system_predictions)
        elif suite == "finrca":
            baseline_metrics, _, _ = run_finrca(root, baseline_predictions)
            system_metrics, _, _ = run_finrca(root, system_predictions)
        elif suite == "finbalance":
            baseline_metrics, _, _ = run_finbalance(root, baseline_predictions)
            system_metrics, _, _ = run_finbalance(root, system_predictions)
        else:
            raise ValueError(f"unknown suite {suite!r}")
        baseline_suites.append(baseline_metrics)
        system_suites.append(system_metrics)

    comparison = compare_systems(
        SystemRunResult(system_name=baseline_name, suites=tuple(baseline_suites)),
        SystemRunResult(system_name=system_name, suites=tuple(system_suites)),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json_report(
        output_dir / "benchmark_result.json", build_report_payload(comparison)
    )
    markdown_path = write_markdown_report(output_dir / "benchmark_report.md", comparison)
    return json_path, markdown_path


def run_demo(
    *,
    demo_dir: Path,
    output_dir: Path,
    seed: int = 20260906,
) -> tuple[Path, Path]:
    """Seed the Phase 19 demo pack and write baseline-vs-system reports."""
    seed_demo_data(demo_dir, seed=seed)
    run_demo_benchmark(demo_dir, output_dir)
    return output_dir / "benchmark.json", output_dir / "benchmark.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m evaluation",
        description="Run Phase 6 offline evaluation benchmarks and emit JSON/markdown reports.",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES,
        help="Root directory containing reconriver/, finrca/, and finbalance/ packs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/reports/out"),
        help="Directory for benchmark JSON/markdown reports",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=("reconriver", "finrca", "finbalance", "all"),
        help="Suite to run; repeatable. Default: all. Ignored when --demo-dir is set.",
    )
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=None,
        help="Seed and evaluate the Phase 19 custom demo pack in this directory",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260906,
        help="Generator seed used with --demo-dir (default: 20260906)",
    )
    parser.add_argument("--baseline-name", default="deterministic-only")
    parser.add_argument("--system-name", default="system")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.demo_dir is not None:
        json_path, markdown_path = run_demo(
            demo_dir=args.demo_dir,
            output_dir=args.output,
            seed=args.seed,
        )
    else:
        selected = args.suite or ["all"]
        if "all" in selected:
            suites = ("reconriver", "finrca", "finbalance")
        else:
            suites = tuple(dict.fromkeys(selected))
        json_path, markdown_path = run_benchmark(
            fixtures_root=args.fixtures,
            output_dir=args.output,
            suites=suites,
            baseline_name=args.baseline_name,
            system_name=args.system_name,
        )
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
