"""Phase 5 ML training entrypoints under Agent F ownership."""

from .fixtures import build_synthetic_pair_cases, write_synthetic_pairs
from .pipeline import TrainMlResult, train_ml_pipeline, write_metrics_report

__all__ = [
    "TrainMlResult",
    "build_synthetic_pair_cases",
    "train_ml_pipeline",
    "write_metrics_report",
    "write_synthetic_pairs",
]
