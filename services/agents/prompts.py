"""Evidence-only prompt packages for bounded application-agent model calls."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import Field

from packages.contracts.models import ContractModel


class AgentTask(StrEnum):
    EXTRACTION = "extraction"
    INVESTIGATION = "investigation"
    SUMMARY = "summary"
    REVIEW_EXPLANATION = "review_explanation"


class EvidencePrompt(ContractModel):
    task: AgentTask
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=30)
    expected_schema: dict[str, Any]
    instructions: str | None = Field(default=None, max_length=2_000)


_TASK_INSTRUCTIONS = {
    AgentTask.EXTRACTION: (
        "Extract only fields supported by the supplied page tokens, cells, headings, and "
        "footnotes. "
        "Preserve source values; do not perform accounting calculations."
    ),
    AgentTask.INVESTIGATION: (
        "Investigate the unresolved exception using only the supplied candidate records and tool "
        "evidence. Identify support for a root cause; leave it unresolved when support is "
        "insufficient."
    ),
    AgentTask.SUMMARY: (
        "Explain the supplied, already-computed metrics. Do not calculate, modify, or infer "
        "KPI values."
    ),
    AgentTask.REVIEW_EXPLANATION: (
        "Explain the supplied validated decision and its supporting evidence for a human reviewer. "
        "Do not make or change the decision."
    ),
}

_MANDATORY_RULES = (
    "Use supplied evidence only. Do not invent records or facts. Return only JSON matching the "
    "expected schema. Include confidence and unresolved_questions in the output."
)


def build_messages(prompt: EvidencePrompt) -> list[dict[str, str]]:
    """Build a compact, deterministic message package without database content retrieval."""
    system = f"{_TASK_INSTRUCTIONS[prompt.task]} {_MANDATORY_RULES}"
    payload: dict[str, Any] = {
        "task": prompt.task.value,
        "expected_schema": prompt.expected_schema,
        "evidence": prompt.evidence,
    }
    if prompt.instructions:
        payload["additional_instructions"] = prompt.instructions
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
        },
    ]
