"""Phase 6 evaluation harness.

Offline runners for ReconRiver, FinRCA, and FinBalance packs plus a shared metric
engine and baseline-vs-system reporting.

Run the fixture benchmark pack with::

    python -m evaluation --suite all
"""

from evaluation.cli import main, run_benchmark
from evaluation.contracts import (
    BenchmarkComparison,
    CasePrediction,
    ClassificationMetrics,
    CostMetrics,
    RiskMetrics,
    SuiteMetrics,
    SystemRunResult,
)

__all__ = [
    "BenchmarkComparison",
    "CasePrediction",
    "ClassificationMetrics",
    "CostMetrics",
    "RiskMetrics",
    "SuiteMetrics",
    "SystemRunResult",
    "main",
    "run_benchmark",
]
