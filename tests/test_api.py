from io import BytesIO

import fitz
from fastapi.testclient import TestClient
from openpyxl import Workbook

from apps.api.app import create_app
from apps.api.main import app
from evaluation.train_ml import train_ml_pipeline, write_synthetic_pairs
from services.ingestion.worker import run_once


def test_health_and_sample_contract_endpoints() -> None:
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/contracts/sample")
    assert response.status_code == 200
    assert response.json()["invoice_number"] == "INV-1001"
    assert response.json()["amount"] == "1200.00"


def test_app_factory_builds_the_configured_api() -> None:
    configured_app = create_app()

    assert configured_app.title == "Finance Reconciliation API"
    assert configured_app.version == "0.1.0"
    assert {route.path for route in configured_app.routes} >= {
        "/health",
        "/contracts/sample",
        "/dashboard/metrics",
    }


def test_dashboard_metrics_are_available_before_reconciliation(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path / "dashboard.sqlite3")))
    assert client.get("/dashboard/metrics").json() == {
        "transactions_processed": 0,
        "reconciled_count": 0,
        "reconciliation_rate": 0,
        "exception_count": 0,
        "amount_at_risk": "0.00",
        "pending_reviews": 0,
        "automation_rate": 0,
    }


def test_reconciliation_api_supports_many_to_one_and_returns_audit_events(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path / "reconciliation.sqlite3")))
    source = {
        "amount": "40.00",
        "currency": "USD",
        "record_date": "2026-01-10",
    }
    response = client.post(
        "/reconciliation/match",
        json={
            "sources": [source, {**source, "amount": "60.00"}],
            "targets": [{**source, "amount": "100.00"}],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["results"]) == 1
    assert payload["results"][0]["status"] == "MATCHED"
    assert len(payload["results"][0]["source_record_ids"]) == 2
    assert payload["audit_events"][0]["actor"] == "reconciliation_api"


def test_reconciliation_runs_are_persisted_with_an_exception_queue(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path / "runs.sqlite3")))
    record = {"amount": "100.00", "currency": "USD", "record_date": "2026-01-10"}
    response = client.post(
        "/reconciliation/runs",
        json={"sources": [record], "targets": [{**record, "amount": "99.00"}]},
    )

    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "COMPLETED"
    assert len(run["exceptions"]) == 2
    assert client.get(f"/reconciliation/runs/{run['id']}").json()["id"] == run["id"]
    assert (
        client.get(f"/reconciliation/runs/{run['id']}/exceptions").json()["exceptions"]
        == run["exceptions"]
    )
    assert client.get("/reconciliation/runs").json()["runs"][0]["id"] == run["id"]


def test_unresolved_run_investigation_is_persisted_and_audited(tmp_path, monkeypatch) -> None:
    def fake_investigation(**_: object) -> dict[str, object]:
        return {
            "output": {
                "root_cause": "Timing difference",
                "proposed_resolution": "Wait for clearing",
                "confidence": "0.90",
                "unresolved_questions": [],
            },
            "telemetry": {
                "model": "glm-4-7-flash",
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "latency_ms": 15,
                "retry_count": 0,
                "status": "success",
                "estimated_cost": "0",
            },
        }

    monkeypatch.setattr("apps.api.routes.investigate_unresolved_case", fake_investigation)
    client = TestClient(create_app(str(tmp_path / "investigation.sqlite3")))
    record = {"amount": "10.00", "currency": "USD", "record_date": "2026-01-10"}
    run = client.post(
        "/reconciliation/runs",
        json={"sources": [record], "targets": [{**record, "amount": "11.00"}]},
    ).json()

    response = client.post(f"/reconciliation/runs/{run['id']}/investigate")
    assert response.status_code == 200
    assert response.json()["output"]["root_cause"] == "Timing difference"
    saved = client.get(f"/reconciliation/runs/{run['id']}/investigations").json()
    assert len(saved["investigations"]) == 1
    assert client.get("/agent-traces").json()["traces"][0]["id"] == response.json()["id"]
    events = client.get("/audit/events").json()["events"]
    assert events[0]["event_type"] == "INVESTIGATION_COMPLETED"


def test_ml_review_api_is_fail_closed_and_returns_review_only_suggestions(tmp_path) -> None:
    unconfigured = TestClient(create_app(str(tmp_path / "unconfigured.sqlite3")))
    candidate = {
        "id": "candidate-1",
        "sources": [
            {
                "id": "payment-1",
                "record_type": "payment",
                "amount": "100.00",
                "currency": "USD",
                "record_date": "2026-01-01",
                "reference": "INV-1",
                "party": "vendor-1",
            }
        ],
        "targets": [
            {
                "id": "settlement-1",
                "record_type": "settlement",
                "amount": "100.00",
                "currency": "USD",
                "record_date": "2026-01-01",
                "reference": "INV-1",
                "party": "vendor-1",
            }
        ],
        "graph_score": "0.95",
    }
    unavailable = unconfigured.post("/demo/ml-review", json={"candidates": [candidate]})
    assert unavailable.status_code == 503

    dataset = write_synthetic_pairs(tmp_path / "pairs.jsonl", worlds=18)
    artifact_dir = tmp_path / "phase5-artifact"
    train_ml_pipeline(dataset, artifact_dir, seed=13)
    client = TestClient(
        create_app(str(tmp_path / "configured.sqlite3"), ml_model_directory=artifact_dir)
    )
    response = client.post("/demo/ml-review", json={"candidates": [candidate]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "REVIEW_ONLY"
    assert payload["suggestions"][0]["automatic_action_eligible"] is False
    assert payload["suggestions"][0]["suggestion"] in {"REVIEW", "UNRESOLVED"}


def test_csv_upload_returns_normalized_records_and_preview(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path / "preview.sqlite3")))
    response = client.post(
        "/documents/upload",
        files={
            "file": (
                "invoices.csv",
                b'invoice number,amount,date,currency\nINV-2,"(1,200.50)",2026-02-01,USD\n',
                "text/csv",
            )
        },
        data={"record_type": "invoice"},
    )

    assert response.status_code == 200
    payload = response.json()
    document_id = payload["document"]["id"]
    run_once(client.app.state.document_store)
    status = client.get(f"/documents/{document_id}").json()
    parsed = client.get(f"/documents/{document_id}/preview").json()
    assert status["status"] == "PARSED"
    assert status["record_count"] == 1
    assert parsed["records"][0]["invoice_number"] == "INV-2"
    assert parsed["records"][0]["amount"] == "-1200.50"
    assert parsed["records"][0]["provenance"]["row_number"] == 2

    document = client.get(f"/documents/{document_id}")
    preview = client.get(f"/documents/{document_id}/preview")
    assert document.status_code == 200
    assert document.json()["record_count"] == 1
    assert preview.status_code == 200
    assert preview.json()["rows"][0]["invoice number"] == "INV-2"


def test_upload_rejects_unsupported_files(tmp_path) -> None:
    response = TestClient(create_app(str(tmp_path / "unsupported.sqlite3"))).post(
        "/documents/upload",
        files={"file": ("records.txt", b"not supported", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV, XLSX, and PDF uploads are supported"


def test_pdf_upload_extracts_native_text_and_coordinates(tmp_path) -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Invoice INV-7    Amount 125.00")
    pdf_content = document.tobytes()
    document.close()

    client = TestClient(create_app(str(tmp_path / "pdf.sqlite3")))
    response = client.post(
        "/documents/upload",
        files={"file": ("invoice.pdf", pdf_content, "application/pdf")},
        data={"record_type": "invoice"},
    )

    assert response.status_code == 200
    document_id = response.json()["document"]["id"]
    run_once(client.app.state.document_store)
    preview = client.get(f"/documents/{document_id}/preview").json()
    assert preview["records"] == []
    assert preview["errors"] == []
    assert preview["rows"][0]["page_number"] == 1
    assert "INV-7" in preview["rows"][0]["text"]
    assert preview["rows"][0]["words"][0]["x0"] == 72.0
    events = client.get(f"/documents/{document_id}/audit").json()["events"]
    assert events[-1]["event_type"] == "INGESTION_COMPLETED"


def test_csv_upload_returns_parsed_records(tmp_path) -> None:
    client = TestClient(create_app(str(tmp_path / "parsed.sqlite3")))
    csv_content = b"invoice_number,amount,date,currency\nINV-2,10.00,2026-01-01,USD\n"

    response = client.post(
        "/documents/upload",
        files={"file": ("invoices.csv", BytesIO(csv_content), "text/csv")},
        data={"record_type": "invoice"},
    )

    assert response.status_code == 200
    payload = response.json()
    run_once(client.app.state.document_store)
    status = client.get(f"/documents/{payload['document']['id']}").json()
    parsed = client.get(f"/documents/{payload['document']['id']}/preview").json()
    assert status["status"] == "PARSED"
    assert status["record_count"] == 1
    assert parsed["records"][0]["invoice_number"] == "INV-2"
    assert parsed["records"][0]["amount"] == "10.00"


def test_upload_is_persistent_idempotent_audited_and_confirmable(tmp_path) -> None:
    database_path = tmp_path / "ingestion.sqlite3"
    csv_content = b"invoice_number,amount,date,currency\nINV-3,25.00,2026-01-01,USD\n"
    first_client = TestClient(create_app(str(database_path)))

    first = first_client.post(
        "/documents/upload",
        files={"file": ("invoices.csv", csv_content, "text/csv")},
        data={"record_type": "invoice"},
    )
    document_id = first.json()["document"]["id"]
    run_once(first_client.app.state.document_store)
    duplicate = first_client.post(
        "/documents/upload",
        files={"file": ("renamed.csv", csv_content, "text/csv")},
        data={"record_type": "invoice"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["duplicate"] is True
    assert duplicate.json()["document"]["id"] == document_id

    second_client = TestClient(create_app(str(database_path)))
    stored = second_client.get(f"/documents/{document_id}")
    assert stored.json()["status"] == "PARSED"
    confirmed = second_client.post(f"/documents/{document_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"
    events = second_client.get(f"/documents/{document_id}/audit").json()["events"]
    assert [event["event_type"] for event in events] == [
        "UPLOAD_RECEIVED",
        "INGESTION_STARTED",
        "INGESTION_COMPLETED",
        "IMPORT_CONFIRMED",
    ]


def test_xlsx_upload_and_row_errors_are_exposed(tmp_path) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["invoice_number", "amount", "date", "currency"])
    worksheet.append(["INV-4", 40, "2026-01-01", "USD"])
    worksheet.append(["INV-5", "bad", "2026-01-02", "USD"])
    buffer = BytesIO()
    workbook.save(buffer)

    client = TestClient(create_app(str(tmp_path / "ingestion.sqlite3")))
    response = client.post(
        "/documents/upload",
        files={
            "file": (
                "invoices.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        data={"record_type": "invoice"},
    )

    assert response.status_code == 200
    payload = response.json()
    run_once(client.app.state.document_store)
    status = client.get(f"/documents/{payload['document']['id']}").json()
    assert status["status"] == "FAILED"
    assert status["record_count"] == 1
    assert status["error_count"] == 1
    errors = client.get(f"/documents/{payload['document']['id']}/errors").json()["errors"]
    assert errors[0]["row_number"] == 3
    assert client.post(f"/documents/{payload['document']['id']}/confirm").status_code == 409


def test_worker_retries_when_object_storage_temporarily_fails(tmp_path) -> None:
    database_path = tmp_path / "retry.sqlite3"
    client = TestClient(create_app(str(database_path)))
    response = client.post(
        "/documents/upload",
        files={
            "file": (
                "retry.csv",
                b"invoice_number,amount,date,currency\nINV-6,60,2026-01-01,USD\n",
                "text/csv",
            )
        },
        data={"record_type": "invoice"},
    )
    document_id = response.json()["document"]["id"]
    store = client.app.state.document_store
    object_path = store.objects.root / f"documents/{document_id}/retry.csv"
    object_path.unlink()

    assert run_once(store) is True
    status = client.get(f"/documents/{document_id}").json()
    assert status["status"] == "UPLOADED"
    assert "Retry scheduled" in status["progress_message"]
    events = client.get(f"/documents/{document_id}/audit").json()["events"]
    assert events[-1]["event_type"] == "INGESTION_RETRY_SCHEDULED"
