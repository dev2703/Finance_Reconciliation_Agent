"""Stripe Sandbox connector for payments, events, and settlement-like records."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from packages.contracts import FinancialRecord, Payment, Provenance, Settlement


class StripeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STRIPE_", extra="ignore")

    secret_key: SecretStr
    base_url: str = "https://api.stripe.com"
    timeout_seconds: float = 20.0


class StripeConnectorError(RuntimeError):
    pass


class StripeSandboxConnector:
    """Minimal Stripe REST adapter; use a Sandbox-restricted secret key only."""

    def __init__(
        self, settings: StripeSettings, *, http_client: httpx.Client | None = None
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=settings.timeout_seconds)

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def create_test_payment(
        self, *, amount: Decimal, currency: str, metadata: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Create a Sandbox PaymentIntent. Stripe receives integer minor units."""
        minor = self._to_minor_units(amount, currency)
        data: dict[str, str] = {"amount": str(minor), "currency": currency.lower()}
        for key, value in (metadata or {}).items():
            data[f"metadata[{key}]"] = value
        return self._request("POST", "/v1/payment_intents", data=data)

    def fetch_payments(
        self, *, starting_after: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        return self._request("GET", "/v1/payment_intents", params=params).get("data", [])

    def fetch_events(
        self, *, event_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"limit": limit}
        if event_type:
            params["type"] = event_type
        return self._request("GET", "/v1/events", params=params).get("data", [])

    def fetch_balance_transactions(
        self, *, payout_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {"limit": limit}
        if payout_id:
            params["payout"] = payout_id
        return self._request("GET", "/v1/balance_transactions", params=params).get("data", [])

    def normalize_payment(self, raw: Mapping[str, Any]) -> Payment:
        identifier = self._required_string(raw, "id")
        return Payment(
            external_id=identifier,
            amount=self._from_minor_units(raw["amount"], str(raw.get("currency") or "usd")),
            currency=str(raw.get("currency") or "USD").upper(),
            record_date=self._timestamp_date(raw.get("created")),
            description=str(raw.get("description") or "Stripe payment"),
            payment_reference=identifier,
            payer_id=raw.get("customer"),
            payment_method=raw.get("payment_method_types", ["stripe"])[0],
            metadata={
                "provider": "stripe",
                "status": raw.get("status"),
                "livemode": raw.get("livemode"),
            },
            provenance=self._provenance(raw, "normalized payment intent"),
        )

    def normalize_settlement(self, raw: Mapping[str, Any]) -> Settlement:
        identifier = self._required_string(raw, "id")
        currency = str(raw.get("currency") or "USD").upper()
        fee = self._from_minor_units(raw.get("fee", 0), currency)
        return Settlement(
            external_id=identifier,
            amount=self._from_minor_units(raw["net"], currency),
            currency=currency,
            record_date=self._timestamp_date(raw.get("created")),
            description=str(raw.get("description") or "Stripe balance transaction"),
            settlement_reference=identifier,
            processor="stripe",
            fee_amount=abs(fee),
            settled_date=self._timestamp_date(raw.get("available_on") or raw.get("created")),
            metadata={"provider": "stripe", "type": raw.get("type"), "payout": raw.get("payout")},
            provenance=self._provenance(raw, "normalized balance transaction"),
        )

    def normalize_many(self, payments: list[Mapping[str, Any]]) -> list[FinancialRecord]:
        return [self.normalize_payment(payment) for payment in payments]

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._http.request(
            method,
            f"{self.settings.base_url.rstrip('/')}{path}",
            auth=(self.settings.secret_key.get_secret_value(), ""),
            timeout=self.settings.timeout_seconds,
            **kwargs,
        )
        try:
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise StripeConnectorError(f"Stripe Sandbox request failed for {path}: {exc}") from exc
        if body.get("error"):
            raise StripeConnectorError(str(body["error"].get("message", "Stripe API error")))
        return body

    @staticmethod
    def _from_minor_units(value: Any, currency: str) -> Decimal:
        # Sandbox MVP supports Stripe's common two-decimal currencies explicitly.
        if currency.upper() in {"JPY", "KRW"}:
            return Decimal(str(value))
        return Decimal(str(value)) / Decimal(100)

    @classmethod
    def _to_minor_units(cls, amount: Decimal, currency: str) -> int:
        multiplier = Decimal(1) if currency.upper() in {"JPY", "KRW"} else Decimal(100)
        minor = amount * multiplier
        if minor != minor.to_integral_value() or amount <= 0:
            raise StripeConnectorError(
                "amount must be positive and representable in Stripe minor units"
            )
        return int(minor)

    @staticmethod
    def _timestamp_date(value: Any) -> datetime.date:
        if not isinstance(value, int | float):
            raise StripeConnectorError("Stripe payload is missing numeric created timestamp")
        return datetime.fromtimestamp(value, tz=UTC).date()

    @staticmethod
    def _required_string(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise StripeConnectorError(f"Stripe payload is missing {field}")
        return value

    @staticmethod
    def _provenance(raw: Mapping[str, Any], action: str) -> Provenance:
        return Provenance(
            source_name="stripe_sandbox",
            source_type="connector",
            original_fields={key: str(value) for key, value in raw.items() if value is not None},
            transformation_history=["fetched from Stripe Sandbox", action],
        )
