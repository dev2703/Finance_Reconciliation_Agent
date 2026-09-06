"""Tests for demo orchestration and Phase 10/20 API surface."""

from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.app import create_app
from evaluation.demo import build_demo_cases
from services.demo import financial_pairs_from_demo_cases, run_reconciliation


def test_demo_orchestration_produces_matches_and_exceptions():
    cases = list(build_demo_cases())
    sources, targets = financial_pairs_from_demo_cases(cases)
    outcome = run_reconciliation(sources, targets)
    assert outcome["matched_count"] + outcome["exception_count"] == len(outcome["results"])
    assert outcome["matched_count"] > 0
    assert outcome["exception_count"] > 0


def test_demo_seed_and_run_persists_run_review_and_reports(tmp_path):
    client = TestClient(create_app(str(tmp_path / "demo.sqlite3")))
    response = client.post("/demo/seed-and-run")
    assert response.status_code == 200
    payload = response.json()
    assert payload["case_count"] == 40
    assert payload["run"]["status"] == "COMPLETED"
    assert payload["matched_count"] > 0
    assert payload["exception_count"] > 0
    assert payload["review"] is not None
    assert payload["review"]["status"] == "PENDING"

    run_id = payload["run"]["id"]
    review_id = payload["review"]["id"]
    assert client.get(f"/reconciliation/runs/{run_id}/exceptions").json()["exceptions"]
    assert client.get("/reviews/pending").json()["reviews"][0]["id"] == review_id

    decided = client.post(
        f"/reviews/{review_id}/decision",
        json={
            "decision": "AUTO_APPROVE",
            "actor": "tester",
            "reason": "Evidence reviewed in test",
        },
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "AUTO_APPROVE"
    assert client.get("/reviews/pending").json()["reviews"] == []

    reports = client.get("/reports/operational").json()
    assert reports["reconciliation"]["run_count"] == 1
    assert reports["exceptions"]["exception_count"] == payload["exception_count"]
    assert reports["audit"]["event_count"] >= 2

    metrics = client.get("/dashboard/metrics").json()
    assert metrics["reconciled_count"] == payload["matched_count"]
    assert metrics["exception_count"] == payload["exception_count"]
    assert metrics["pending_reviews"] == 0
