"""Bounded state and contracts for evidence-driven investigation agents."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import Field

from packages.contracts.models import ContractModel, EvidenceItem


class AgentKind(StrEnum):
    INVESTIGATION = "investigation"
    EXTRACTION = "extraction"
    SUMMARY = "summary"
    REVIEW_EXPLANATION = "review_explanation"


class AgentRunRequest(ContractModel):
    agent: AgentKind
    case_id: str
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=30)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(ContractModel):
    agent: AgentKind
    case_id: str
    conclusion: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class InvestigationLimits(ContractModel):
    max_llm_turns: int = Field(default=4, ge=0)
    max_tool_calls: int = Field(default=8, ge=0)
    max_context_bytes: int = Field(default=100_000, gt=0)


class InvestigationBudget:
    """Enforces turn/tool/context budgets and blocks repeated identical tool calls."""

    def __init__(self, limits: InvestigationLimits = InvestigationLimits()) -> None:
        self.limits = limits
        self.turns = 0
        self.tool_calls = 0
        self.context_bytes = 0
        self._tool_signatures: set[str] = set()

    def register_turn(self) -> None:
        if self.turns >= self.limits.max_llm_turns:
            raise RuntimeError("Investigation LLM-turn limit reached")
        self.turns += 1

    def register_tool_call(self, tool_name: str, arguments: dict[str, Any], result: Any) -> None:
        signature = json.dumps([tool_name, arguments], sort_keys=True, default=str)
        if signature in self._tool_signatures:
            raise RuntimeError("Duplicate investigation tool call")
        if self.tool_calls >= self.limits.max_tool_calls:
            raise RuntimeError("Investigation tool-call limit reached")
        encoded_size = len(json.dumps(result, sort_keys=True, default=str).encode())
        if self.context_bytes + encoded_size > self.limits.max_context_bytes:
            raise RuntimeError("Investigation context limit reached")
        self._tool_signatures.add(signature)
        self.tool_calls += 1
        self.context_bytes += encoded_size
