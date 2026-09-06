"""Synthetic custom-pair fixtures for Phase 5 ML training."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


def _record(
    record_id: str,
    *,
    record_type: str,
    amount: str,
    day: date,
    reference: str,
    party: str,
    description: str,
) -> dict:
    return {
        "id": record_id,
        "record_type": record_type,
        "amount": amount,
        "currency": "USD",
        "record_date": day.isoformat(),
        "reference": reference,
        "party": party,
        "description": description,
    }


def _case(
    *,
    case_id: str,
    scenario_id: str,
    generator_seed: int,
    entity_id: str,
    is_match: bool,
    is_hard_negative: bool,
    source: dict,
    target: dict,
    graph_score: str,
) -> dict:
    return {
        "case_id": case_id,
        "scenario_id": scenario_id,
        "generator_seed": generator_seed,
        "group_entity_ids": [entity_id, source["id"], target["id"]],
        "label": "MATCH" if is_match else ("HARD_NEGATIVE" if is_hard_negative else "NEGATIVE"),
        "ground_truth": {
            "is_match": is_match,
            "is_hard_negative": is_hard_negative,
            "source_ids": [source["id"]],
            "target_ids": [target["id"]],
            "graph_score": graph_score,
            "expected_amount": source["amount"],
        },
        "records": [source, target],
    }


def build_synthetic_pair_cases(worlds: int = 18) -> list[dict]:
    """Create disconnected worlds with positives, easy negatives, and hard negatives."""
    if worlds < 6:
        raise ValueError("At least six worlds are required for train/validation/test holdouts")
    cases: list[dict] = []
    base = date(2026, 1, 1)
    for world in range(worlds):
        seed = 1000 + world
        entity = f"vendor-{world}"
        day = base + timedelta(days=world)
        amount = str(Decimal("100.00") + Decimal(world))
        payment = _record(
            f"pay-{world}",
            record_type="payment",
            amount=amount,
            day=day,
            reference=f"INV-{world}",
            party=entity,
            description=f"Payment world {world}",
        )
        settlement = _record(
            f"set-{world}",
            record_type="settlement",
            amount=amount,
            day=day,
            reference=f"INV-{world}",
            party=entity,
            description=f"Settlement world {world}",
        )
        cases.append(
            _case(
                case_id=f"match-{world}",
                scenario_id=f"exact-{world}",
                generator_seed=seed,
                entity_id=entity,
                is_match=True,
                is_hard_negative=False,
                source=payment,
                target=settlement,
                graph_score="0.95",
            )
        )

        easy_negative = _record(
            f"set-easy-{world}",
            record_type="settlement",
            amount=str(Decimal(amount) + Decimal("37.50")),
            day=day + timedelta(days=12),
            reference=f"OTHER-{world}",
            party=f"other-{world}",
            description="Unrelated settlement",
        )
        cases.append(
            _case(
                case_id=f"neg-easy-{world}",
                scenario_id=f"easy-neg-{world}",
                generator_seed=seed + 10_000,
                entity_id=f"easy-{world}",
                is_match=False,
                is_hard_negative=False,
                source=payment,
                target=easy_negative,
                graph_score="0.10",
            )
        )

        # Hard negative: same amount and party, wrong reference/date.
        hard = _record(
            f"set-hard-{world}",
            record_type="settlement",
            amount=amount,
            day=day + timedelta(days=9),
            reference=f"INV-{world}-WRONG",
            party=entity,
            description="Same party wrong invoice",
        )
        cases.append(
            _case(
                case_id=f"neg-hard-{world}",
                scenario_id=f"hard-neg-{world}",
                generator_seed=seed + 20_000,
                entity_id=f"hard-{world}",
                is_match=False,
                is_hard_negative=True,
                source=payment,
                target=hard,
                graph_score="0.55",
            )
        )
    return cases


def write_synthetic_pairs(path: str | Path, *, worlds: int = 18) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = build_synthetic_pair_cases(worlds=worlds)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path
