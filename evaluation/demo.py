"""Deterministic Phase 19 demo-pack construction."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

CASE_COUNTS: Mapping[str, int] = {
    "EXACT_MATCH": 10,
    "TIMING_DIFFERENCE": 5,
    "KNOWN_FEE": 5,
    "PARTIAL_PAYMENT": 3,
    "SPLIT_SETTLEMENT": 3,
    "DUPLICATE": 2,
    "WRONG_ALLOCATION": 2,
    "MISSING_BANK_TRANSACTION": 2,
    "MISSING_LEDGER_TRANSACTION": 2,
    "HARD_NEGATIVE": 2,
    "MULTI_HOP": 2,
    "MESSY_PDF_TABLE": 2,
}


def _case(label: str, index: int, seed: int) -> dict[str, Any]:
    slug = label.casefold().replace("_", "-")
    case_id = f"demo-{slug}-{index:02d}"
    amount = Decimal(100 + index)
    expected_exception = label not in {"EXACT_MATCH", "HARD_NEGATIVE"}
    source_amount = amount
    target_amount = amount
    if label == "KNOWN_FEE":
        target_amount -= Decimal("2.50")
    elif label in {"PARTIAL_PAYMENT", "SPLIT_SETTLEMENT"}:
        target_amount /= Decimal(2)
    elif label == "WRONG_ALLOCATION":
        target_amount += Decimal(10)

    return {
        "case_id": case_id,
        "scenario_id": slug,
        "generator_seed": seed,
        "group_entity_ids": [f"source-{case_id}", f"target-{case_id}"],
        "label": label,
        "ground_truth": {
            "expected_outcome": label,
            "detected_exception": expected_exception,
            "root_cause": slug if expected_exception else None,
            "resolution": "human_review" if expected_exception else "reconcile",
            "evidence_ids": [f"evidence-{case_id}"],
            "amount": format(amount, "f"),
        },
        "records": [
            {
                "id": f"source-{case_id}",
                "record_type": "invoice",
                "amount": format(source_amount, "f"),
                "currency": "AUD",
                "reference": f"REF-{index:04d}",
                "evidence_id": f"evidence-{case_id}",
            },
            {
                "id": f"target-{case_id}",
                "record_type": "payment",
                "amount": format(target_amount, "f"),
                "currency": "AUD",
                "reference": f"REF-{index:04d}",
            },
        ],
    }


def build_demo_cases(*, seed: int = 20260906) -> tuple[dict[str, Any], ...]:
    """Build the stable 40-case pack required by the Phase 19 roadmap."""
    cases: list[dict[str, Any]] = []
    index = 1
    for label, count in CASE_COUNTS.items():
        for _ in range(count):
            cases.append(_case(label, index, seed))
            index += 1
    return tuple(cases)


def _prediction(case: Mapping[str, Any], *, baseline: bool) -> dict[str, Any]:
    truth = case["ground_truth"]
    label = "EXACT_MATCH" if baseline else case["label"]
    detected = False if baseline else truth["detected_exception"]
    return {
        "case_id": case["case_id"],
        "predicted_label": label,
        "detected_exception": detected,
        "root_cause": None if baseline else truth["root_cause"],
        "evidence_ids": [] if baseline else truth["evidence_ids"],
        "resolution": "reconcile" if baseline else truth["resolution"],
        "auto_resolved": (not detected if baseline else case["label"] == "EXACT_MATCH"),
        "amount": truth["amount"],
        "latency_ms": "1",
        "llm_tokens": 0,
        "estimated_cost": "0",
    }


def seed_demo_data(output_dir: str | Path, *, seed: int = 20260906) -> dict[str, Path]:
    """Write ground truth and reproducible baseline/candidate predictions."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    cases = build_demo_cases(seed=seed)
    paths = {
        "cases": output / "cases.jsonl",
        "baseline": output / "baseline_predictions.jsonl",
        "system": output / "system_predictions.jsonl",
        "manifest": output / "manifest.json",
    }
    paths["cases"].write_text(
        "".join(f"{json.dumps(case, sort_keys=True)}\n" for case in cases), encoding="utf-8"
    )
    for name, baseline in (("baseline", True), ("system", False)):
        paths[name].write_text(
            "".join(
                f"{json.dumps(_prediction(case, baseline=baseline), sort_keys=True)}\n"
                for case in cases
            ),
            encoding="utf-8",
        )
    paths["manifest"].write_text(
        json.dumps(
            {"seed": seed, "case_count": len(cases), "case_counts": CASE_COUNTS},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return paths
