"""Train the Phase 5 ML matcher from a custom pair JSONL dataset.

Example:

    python -m evaluation.train_ml \\
      --dataset evaluation/train_ml/data/synthetic_pairs.jsonl \\
      --artifact-dir artifacts/phase5-ml \\
      --report artifacts/phase5-ml/metrics.json
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path

from services.ml.calibration import ThresholdConstraint

from .fixtures import write_synthetic_pairs
from .pipeline import train_ml_pipeline, write_metrics_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Custom pair JSONL path")
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        required=True,
        help="Directory for model.joblib and model.json",
    )
    parser.add_argument("--report", type=Path, default=None, help="Optional metrics JSON path")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-version", default="phase5-ml-v1")
    parser.add_argument(
        "--write-synthetic",
        action="store_true",
        help="Create --dataset as the bundled synthetic fixture before training",
    )
    parser.add_argument("--synthetic-worlds", type=int, default=18)
    parser.add_argument("--review-max-fp-rate", type=float, default=0.25)
    parser.add_argument("--review-max-fp-exposure", default="500")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write_synthetic:
        write_synthetic_pairs(args.dataset, worlds=args.synthetic_worlds)
    result = train_ml_pipeline(
        args.dataset,
        args.artifact_dir,
        seed=args.seed,
        model_version=args.model_version,
        review_constraint=ThresholdConstraint(
            max_false_positive_rate=args.review_max_fp_rate,
            max_false_positive_exposure=Decimal(args.review_max_fp_exposure),
        ),
    )
    if args.report is not None:
        write_metrics_report(result, args.report)
    print(
        f"trained {result.best_model_name} "
        f"gate_passed={result.review_gate_passed} "
        f"artifact={result.artifact_directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
