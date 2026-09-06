from datetime import date
from decimal import Decimal

from pydantic import Field, field_validator, model_validator

from packages.contracts.models import ContractModel


class ObservableRecord(ContractModel):
    id: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    amount: Decimal
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    record_date: date
    reference: str | None = None
    party: str | None = None
    description: str | None = None

    @field_validator("amount")
    @classmethod
    def finite_amount(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Amount must be finite")
        return value


class Candidate(ContractModel):
    id: str = Field(min_length=1)
    sources: list[ObservableRecord] = Field(min_length=1, max_length=8)
    targets: list[ObservableRecord] = Field(min_length=1, max_length=8)
    graph_score: Decimal | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def distinct_records(self):
        ids = [record.id for record in self.sources + self.targets]
        if len(ids) != len(set(ids)):
            raise ValueError("Candidate contains duplicate record IDs")
        return self
