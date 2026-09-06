"""Bounded unresolved-case investigation through the configured TensorMux gateway."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import neatlogs
from pydantic import Field

from packages.contracts.models import ContractModel
from services.agents.prompts import AgentTask, EvidencePrompt
from services.agents.runtime import InvestigationBudget, InvestigationLimits
from services.agents.tensormux import TensorMuxClient, TensorMuxSettings


class InvestigationFinding(ContractModel):
    root_cause: str | None = None
    proposed_resolution: str | None = None
    confidence: Decimal = Field(ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)


@neatlogs.span(kind="CHAIN")
def investigate_unresolved_case(
    *,
    case_id: str,
    evidence: list[dict[str, Any]],
    settings: TensorMuxSettings | None = None,
) -> dict[str, Any]:
    """Make one evidence-only call; accounting state is never mutated here."""
    budget = InvestigationBudget(InvestigationLimits(max_llm_turns=1, max_tool_calls=0))
    budget.register_turn()
    prompt = EvidencePrompt(
        task=AgentTask.INVESTIGATION,
        evidence=evidence[:30],
        expected_schema=InvestigationFinding.model_json_schema(),
    )
    with TensorMuxClient(settings or TensorMuxSettings()) as client:
        result = client.generate_structured(
            prompt,
            InvestigationFinding,
            case_id=case_id,
            agent_run_id=case_id,
        )
    return {
        "output": result.output.model_dump(mode="json"),
        "telemetry": result.telemetry.model_dump(mode="json"),
    }
