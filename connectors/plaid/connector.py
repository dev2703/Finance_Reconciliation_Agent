"""Plaid Sandbox adapter.

The connector deliberately exposes raw provider payloads at its HTTP boundary and
normalizes them immediately into canonical records.  This keeps Plaid-specific
fields out of reconciliation code and makes the sandbox client mockable.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from packages.contracts import BankTransaction, FinancialRecord, Provenance


class PlaidSettings(BaseSettings):
    """Configuration for a Plaid Sandbox-only client."""

    model_config = SettingsConfigDict(env_prefix="PLAID_", extra="ignore")

    client_id: str
    secret: SecretStr
    base_url: str = "https://sandbox.plaid.com"
    timeout_seconds: float = 20.0


class PlaidConnectorError(RuntimeError):
    """A provider failure with no normalized records produced."""


class PlaidSandboxConnector:
    """Synchronous, injectable Plaid Sandbox client.

    Plaid reports a positive transaction amount for money leaving an account;
    the canonical amount intentionally preserves that source convention.  The
    direction is explicit in ``transaction_type`` and provider metadata.
    """

    def __init__(self, settings: PlaidSettings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=settings.timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> PlaidSandboxConnector:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def create_public_token(self, *, institution_id: str, initial_products: list[str]) -> str:
        """Create a Sandbox Link token for a test Item."""
        payload = self._post(
            "/sandbox/public_token/create",
            {"institution_id": institution_id, "initial_products": initial_products},
        )
        return self._required_string(payload, "public_token")

    def exchange_public_token(self, public_token: str) -> str:
        payload = self._post("/item/public_token/exchange", {"public_token": public_token})
        return self._required_string(payload, "access_token")

    def fetch_transactions(
        self, *, access_token: str, cursor: str | None = None
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch one transactions/sync page and return its next cursor."""
        request: dict[str, Any] = {"access_token": access_token}
        if cursor:
            request["cursor"] = cursor
        payload = self._post("/transactions/sync", request)
        transactions = payload.get("added", []) + payload.get("modified", [])
        if not isinstance(transactions, list):
            raise PlaidConnectorError("Plaid transactions response has invalid transaction arrays")
        return transactions, payload.get("next_cursor")

    def create_sandbox_transactions(
        self, *, access_token: str, account_id: str, transactions: list[dict[str, Any]]
    ) -> None:
        """Add custom transactions to a Sandbox Item for integration tests."""
        self._post(
            "/sandbox/transactions/create",
            {"access_token": access_token, "account_id": account_id, "transactions": transactions},
        )

    def trigger_webhook(self, *, access_token: str, webhook_code: str) -> None:
        """Trigger a documented Sandbox webhook code; no production equivalent is used."""
        self._post(
            "/sandbox/item/fire_webhook",
            {"access_token": access_token, "webhook_code": webhook_code},
        )

    def normalize(self, raw: Mapping[str, Any]) -> BankTransaction:
        """Normalize a Plaid transaction without rounding its Decimal amount."""
        provider_id = self._required_string(raw, "transaction_id")
        amount = Decimal(str(raw["amount"]))
        account_id = self._required_string(raw, "account_id")
        transaction_date = date.fromisoformat(self._required_string(raw, "date"))
        name = str(raw.get("merchant_name") or raw.get("name") or "Plaid transaction")
        payment_channel = str(raw.get("payment_channel") or "unknown")
        return BankTransaction(
            external_id=provider_id,
            amount=amount,
            currency=str(raw.get("iso_currency_code") or "USD").upper(),
            record_date=transaction_date,
            description=name,
            account_id=account_id,
            transaction_type="debit" if amount >= 0 else "credit",
            bank_reference=raw.get("pending_transaction_id") or provider_id,
            value_date=date.fromisoformat(raw["authorized_date"])
            if raw.get("authorized_date")
            else None,
            metadata={
                "provider": "plaid",
                "provider_amount_convention": "positive_is_outflow",
                "payment_channel": payment_channel,
                "pending": bool(raw.get("pending", False)),
                "category": raw.get("personal_finance_category"),
            },
            provenance=Provenance(
                source_name="plaid_sandbox",
                source_type="connector",
                original_fields={
                    key: str(value) for key, value in raw.items() if value is not None
                },
                transformation_history=[
                    "fetched from Plaid Sandbox",
                    "normalized bank transaction",
                ],
            ),
        )

    def normalize_many(self, raw_records: list[Mapping[str, Any]]) -> list[FinancialRecord]:
        return [self.normalize(record) for record in raw_records]

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = {
            "client_id": self.settings.client_id,
            "secret": self.settings.secret.get_secret_value(),
        }
        response = self._http.post(
            f"{self.settings.base_url.rstrip('/')}{path}",
            json=request | payload,
            timeout=self.settings.timeout_seconds,
        )
        try:
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PlaidConnectorError(f"Plaid Sandbox request failed for {path}: {exc}") from exc
        if body.get("error_code"):
            raise PlaidConnectorError(
                f"Plaid Sandbox error {body['error_code']}: {body.get('error_message', '')}"
            )
        return body

    @staticmethod
    def _required_string(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise PlaidConnectorError(f"Plaid payload is missing {field}")
        return value
