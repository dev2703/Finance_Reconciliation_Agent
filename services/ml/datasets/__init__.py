"""Deterministic benchmark adapters for Phase 5 training and evaluation.

The service-local contract is :class:`DatasetCase`. An adapter returns one case
per ground-truth decision and never reads the network.  ``grouping`` carries all
keys that must stay together in grouped train/test splits.  ``ground_truth`` and
``records`` retain the source labels and evidence, with monetary fields converted
to :class:`decimal.Decimal`.  ``provenance`` identifies every local source row.

This module deliberately does not extend the shared canonical schemas: benchmark
labels are training metadata, not accounting records.
"""

from .adapters import load_custom_benchmark, load_finrca, load_reconriver
from .contracts import DatasetCase, DatasetFormatError, DatasetGrouping, SourceRow
from .examples import training_examples_from_cases

__all__ = [
    "DatasetCase",
    "DatasetFormatError",
    "DatasetGrouping",
    "SourceRow",
    "load_custom_benchmark",
    "load_finrca",
    "load_reconriver",
    "training_examples_from_cases",
]
