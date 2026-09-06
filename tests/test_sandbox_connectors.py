from __future__ import annotations

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr

from connectors.plaid import PlaidConnectorError, PlaidSandboxConnector, PlaidSettings
from connectors.stripe import StripeConnectorError, StripeSandboxConnector, StripeSettings


def client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def test_plaid_fetch_simulate_and_normalize_transaction() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        calls.append((request.url.path, payload))
        if request.url.path == "/sandbox/transactions/create":
            return httpx.Response(200, json={"request_id": "req-1"})
        return httpx.Response(
            200,
            json={
                "added": [
                    {
                        "transaction_id": "ptx-1",
                        "account_id": "acct-1",
                        "amount": 12.34,
                        "iso_currency_code": "usd",
                        "date": "2026-09-06",
                        "name": "Coffee",
                        "payment_channel": "in store",
                        "pending": False,
                    }
                ],
                "modified": [],
                "next_cursor": "cursor-2",
            },
        )

    connector = PlaidSandboxConnector(
        PlaidSettings(client_id="client", secret=SecretStr("secret")),
        http_client=client(httpx.MockTransport(handler)),
    )
    connector.create_sandbox_transactions(
        access_token="token", account_id="acct-1", transactions=[]
    )
    raw, cursor = connector.fetch_transactions(access_token="token")
    record = connector.normalize(raw[0])

    assert cursor == "cursor-2"
    assert record.amount == Decimal("12.34")
    assert record.transaction_type == "debit"
    assert record.provenance.source_name == "plaid_sandbox"
    assert calls[0][0] == "/sandbox/transactions/create"
    assert calls[1][1]["client_id"] == "client"


def test_plaid_rejects_provider_error() -> None:
    connector = PlaidSandboxConnector(
        PlaidSettings(client_id="client", secret=SecretStr("secret")),
        http_client=client(
            httpx.MockTransport(lambda _: httpx.Response(400, json={"error_code": "INVALID_INPUT"}))
        ),
    )
    with pytest.raises(PlaidConnectorError):
        connector.fetch_transactions(access_token="token")


def test_stripe_payment_and_settlement_normalization_and_api_shape() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200, json={"id": "pi_test", "amount": 1234, "currency": "usd", "created": 0}
        )

    connector = StripeSandboxConnector(
        StripeSettings(secret_key=SecretStr("sk_test_example")),
        http_client=client(httpx.MockTransport(handler)),
    )
    created = connector.create_test_payment(
        amount=Decimal("12.34"), currency="USD", metadata={"case": "c1"}
    )
    payment = connector.normalize_payment(created)
    settlement = connector.normalize_settlement(
        {
            "id": "txn_1",
            "net": 1140,
            "fee": 94,
            "currency": "usd",
            "created": 0,
            "available_on": 86400,
        }
    )

    assert payment.amount == Decimal("12.34")
    assert payment.payment_reference == "pi_test"
    assert settlement.amount == Decimal("11.4")
    assert settlement.fee_amount == Decimal("0.94")
    assert captured[0].url.path == "/v1/payment_intents"
    assert b"amount=1234" in captured[0].content
    assert captured[0].headers["authorization"].startswith("Basic ")


def test_stripe_rejects_unrepresentable_amount_and_api_error() -> None:
    connector = StripeSandboxConnector(
        StripeSettings(secret_key=SecretStr("sk_test_example")),
        http_client=client(
            httpx.MockTransport(
                lambda _: httpx.Response(401, json={"error": {"message": "bad key"}})
            )
        ),
    )
    with pytest.raises(StripeConnectorError, match="representable"):
        connector.create_test_payment(amount=Decimal("0.001"), currency="USD")
    with pytest.raises(StripeConnectorError, match="Stripe Sandbox"):
        connector.fetch_events()
