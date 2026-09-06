"""Deterministic reconciliation rules and allocation helpers."""

from .engine import (
    allocate_many_to_one,
    allocate_one_to_many,
    match_pair,
    reconcile_records,
)

__all__ = [
    "allocate_many_to_one",
    "allocate_one_to_many",
    "match_pair",
    "reconcile_records",
]
