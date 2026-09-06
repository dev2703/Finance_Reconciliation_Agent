"""Service-local dataset contracts; no shared schema dependency."""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any


class DatasetFormatError(ValueError):
    """Raised when benchmark input cannot be interpreted unambiguously."""


@dataclass(frozen=True)
class SourceRow:
    path: Path
    line: int | None
    sha256: str


@dataclass(frozen=True)
class DatasetGrouping:
    scenario: str
    entity_ids: tuple[str, ...]
    generator_seed: int


@dataclass(frozen=True)
class DatasetCase:
    dataset: str
    case_id: str
    label: str
    grouping: DatasetGrouping
    ground_truth: Mapping[str, Any]
    records: tuple[Mapping[str, Any], ...]
    amounts: tuple[Decimal, ...]
    provenance: tuple[SourceRow, ...]
