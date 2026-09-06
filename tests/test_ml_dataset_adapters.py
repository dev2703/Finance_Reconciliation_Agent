import csv
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from services.ml.datasets import (
    DatasetFormatError,
    load_custom_benchmark,
    load_finrca,
    load_reconriver,
)

RECON_COLUMNS = [
    "scenario_id",
    "result_scope",
    "work_key",
    "settlement_batch_id",
    "internal_payment_id",
    "processor_transaction_id",
    "bank_entry_id",
    "expected_outcome",
    "expected_reason_code",
    "expected_difference",
    "explanation",
]


def write_reconriver(root: Path, *, difference: str = "0.37", scenario: str = "mixed"):
    root.mkdir()
    truth_path = root / "expected_reconciliation.csv"
    with truth_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RECON_COLUMNS)
        writer.writeheader()
        writer.writerow(
            {
                "scenario_id": scenario,
                "result_scope": "ORDER",
                "work_key": "ORDER-1",
                "settlement_batch_id": "",
                "internal_payment_id": "INT-1",
                "processor_transaction_id": "PROC-1",
                "bank_entry_id": "",
                "expected_outcome": "FEE_MISMATCH",
                "expected_reason_code": "L1_CONFIGURED_FEE_POLICY",
                "expected_difference": difference,
                "explanation": "Configured fee differs.",
            }
        )
    checksum = hashlib.sha256(truth_path.read_bytes()).hexdigest()
    (root / "scenario_manifest.json").write_text(
        json.dumps(
            {
                "scenario_id": scenario,
                "random_seed": 42,
                "file_sha256_checksums": {"expected_reconciliation.csv": checksum},
            }
        ),
        encoding="utf-8",
    )
    return truth_path


def write_jsonl(path: Path, rows: list[dict]):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def finrca_truth(**updates):
    row = {
        "case_id": "RCA_1",
        "failure_type": "F14_BANK_ERP_AMOUNT_MISMATCH",
        "scenario_variant": "wrong_bank_amount",
        "group_vendor_id": "VENDOR-1",
        "primary_entity": {"id": "PAY-1", "type": "payment"},
        "affected_entities": [
            {"id": "PAY-1", "type": "payment"},
            {"id": "BANK-1", "type": "bank_transaction"},
        ],
        "evidence_ids": ["PAY-1", "BANK-1"],
        "root_cause": "Bank amount was mutated.",
        "split": "train",
    }
    row.update(updates)
    return row


def write_finrca(root: Path, truth_rows=None, evidence_rows=None):
    root.mkdir()
    (root / "resolved_config.yaml").write_text(yaml.safe_dump({"seed": 73}), encoding="utf-8")
    write_jsonl(root / "rca_ground_truth.jsonl", truth_rows or [finrca_truth()])
    evidence_root = root / "train"
    evidence_root.mkdir()
    write_jsonl(
        evidence_root / "case_entity_records.jsonl",
        evidence_rows
        or [
            {
                "case_id": "RCA_1",
                "table": "payments",
                "record": {
                    "payment_id": "PAY-1",
                    "amount": "1234.56",
                    "unit_price": "2.50",
                },
            },
            {
                "case_id": "RCA_1",
                "table": "bank_transactions",
                "record": {"bank_transaction_id": "BANK-1", "amount": "1230.00"},
            },
        ],
    )


def custom_row(**updates):
    row = {
        "case_id": "CUSTOM-1",
        "scenario_id": "known-fee",
        "generator_seed": 9,
        "group_entity_ids": ["VENDOR-1", "PAY-1"],
        "label": "KNOWN_FEE",
        "ground_truth": {"expected_amount": "1.25", "reason": "processor fee"},
        "records": [{"id": "PAY-1", "amount": "101.25"}],
    }
    row.update(updates)
    return row


def test_reconriver_preserves_ground_truth_grouping_decimal_and_provenance(tmp_path):
    root = tmp_path / "reconriver"
    write_reconriver(root)

    cases = load_reconriver(root)

    assert len(cases) == 1
    case = cases[0]
    assert case.case_id == "mixed:ORDER:ORDER-1"
    assert case.label == "FEE_MISMATCH"
    assert case.grouping.scenario == "mixed"
    assert case.grouping.entity_ids == ("ORDER-1", "INT-1", "PROC-1")
    assert case.grouping.generator_seed == 42
    assert case.ground_truth["expected_reason_code"] == "L1_CONFIGURED_FEE_POLICY"
    assert case.ground_truth["expected_difference"] == Decimal("0.37")
    assert case.amounts == (Decimal("0.37"),)
    assert [(row.path.name, row.line) for row in case.provenance] == [
        ("scenario_manifest.json", None),
        ("expected_reconciliation.csv", 2),
    ]
    assert all(len(row.sha256) == 64 for row in case.provenance)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("checksum", "SHA-256"),
        ("scenario", "scenario_id differs"),
        ("amount", "not a valid decimal"),
    ],
)
def test_reconriver_rejects_corrupt_or_ambiguous_inputs(tmp_path, mutation, message):
    root = tmp_path / "reconriver"
    truth_path = write_reconriver(root, difference="bad" if mutation == "amount" else "0.00")
    if mutation == "checksum":
        truth_path.write_text(truth_path.read_text() + "\n", encoding="utf-8")
    elif mutation == "scenario":
        lines = truth_path.read_text().replace("mixed,ORDER", "other,ORDER")
        truth_path.write_text(lines, encoding="utf-8")
        manifest = json.loads((root / "scenario_manifest.json").read_text())
        manifest["file_sha256_checksums"]["expected_reconciliation.csv"] = hashlib.sha256(
            truth_path.read_bytes()
        ).hexdigest()
        (root / "scenario_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(DatasetFormatError, match=message):
        load_reconriver(root)


def test_finrca_preserves_labels_entities_seed_evidence_and_decimal_amounts(tmp_path):
    root = tmp_path / "finrca"
    write_finrca(root)

    cases = load_finrca(root)

    assert len(cases) == 1
    case = cases[0]
    assert case.dataset == "finrca"
    assert case.label == "F14_BANK_ERP_AMOUNT_MISMATCH"
    assert case.grouping.scenario == "wrong_bank_amount"
    assert case.grouping.entity_ids == ("VENDOR-1", "PAY-1", "BANK-1")
    assert case.grouping.generator_seed == 73
    assert case.ground_truth["root_cause"] == "Bank amount was mutated."
    assert case.records[0]["record"]["amount"] == Decimal("1234.56")
    assert case.records[0]["record"]["unit_price"] == Decimal("2.50")
    assert case.amounts == (Decimal("1234.56"), Decimal("2.50"), Decimal("1230.00"))
    assert [(row.path.name, row.line) for row in case.provenance] == [
        ("resolved_config.yaml", None),
        ("rca_ground_truth.jsonl", 1),
        ("case_entity_records.jsonl", 1),
        ("case_entity_records.jsonl", 2),
    ]


@pytest.mark.parametrize(
    ("truth_rows", "evidence_rows", "message"),
    [
        ([finrca_truth(), finrca_truth()], None, "duplicate case_id"),
        ([finrca_truth(evidence_ids=["MISSING"])], None, "do not resolve"),
        ([finrca_truth(split="test")], None, "evidence split conflicts"),
        ([finrca_truth()], [{"case_id": "OTHER", "table": "x", "record": {}}], "no model-visible"),
        (
            [finrca_truth()],
            [
                {
                    "case_id": "RCA_1",
                    "table": "payments",
                    "record": {"payment_id": "PAY-1", "amount": 1.1},
                },
                {
                    "case_id": "RCA_1",
                    "table": "bank_transactions",
                    "record": {"bank_transaction_id": "BANK-1"},
                },
            ],
            "exact decimal string",
        ),
    ],
)
def test_finrca_rejects_malformed_or_ambiguous_cases(tmp_path, truth_rows, evidence_rows, message):
    root = tmp_path / "finrca"
    write_finrca(root, truth_rows=truth_rows, evidence_rows=evidence_rows)

    with pytest.raises(DatasetFormatError, match=message):
        load_finrca(root)


def test_custom_jsonl_preserves_contract_and_all_exact_money(tmp_path):
    path = tmp_path / "custom.jsonl"
    write_jsonl(path, [custom_row()])

    case = load_custom_benchmark(path)[0]

    assert case.label == "KNOWN_FEE"
    assert case.grouping.scenario == "known-fee"
    assert case.grouping.entity_ids == ("VENDOR-1", "PAY-1")
    assert case.grouping.generator_seed == 9
    assert case.ground_truth["expected_amount"] == Decimal("1.25")
    assert case.records[0]["amount"] == Decimal("101.25")
    assert case.amounts == (Decimal("1.25"), Decimal("101.25"))
    assert case.provenance[0].line == 1


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([custom_row(), custom_row()], "duplicate case_id"),
        ([custom_row(group_entity_ids=["PAY-1", "PAY-1"])], "must be unique"),
        ([custom_row(records=[])], "one or more objects"),
        ([custom_row(records=[{"amount": 12.34}])], "exact decimal string"),
        ([custom_row(extra="unexpected")], "row fields must be exactly"),
    ],
)
def test_custom_jsonl_rejects_malformed_or_ambiguous_rows(tmp_path, rows, message):
    path = tmp_path / "custom.jsonl"
    write_jsonl(path, rows)

    with pytest.raises(DatasetFormatError, match=message):
        load_custom_benchmark(path)


def test_jsonl_rejects_blank_lines(tmp_path):
    path = tmp_path / "custom.jsonl"
    path.write_text(json.dumps(custom_row()) + "\n\n", encoding="utf-8")

    with pytest.raises(DatasetFormatError, match="blank JSONL"):
        load_custom_benchmark(path)
