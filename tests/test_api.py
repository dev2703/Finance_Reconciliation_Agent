from fastapi.testclient import TestClient

from apps.api.main import app


def test_health_and_sample_contract_endpoints() -> None:
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/contracts/sample")
    assert response.status_code == 200
    assert response.json()["invoice_number"] == "INV-1001"
    assert response.json()["amount"] == "1200.00"
