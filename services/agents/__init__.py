"""Bounded runtime agent contracts and model gateway."""

from services.agents.controller import InvestigationFinding, investigate_unresolved_case
from services.agents.prompts import AgentTask, EvidencePrompt, build_messages
from services.agents.runtime import (
    AgentKind,
    AgentRunRequest,
    AgentRunResult,
    InvestigationBudget,
    InvestigationLimits,
)
from services.agents.tensormux import (
    ModelCallTelemetry,
    StructuredModelResult,
    TensorMuxClient,
    TensorMuxError,
    TensorMuxSettings,
)

__all__ = [
    "InvestigationFinding",
    "AgentTask",
    "AgentKind",
    "AgentRunRequest",
    "AgentRunResult",
    "EvidencePrompt",
    "InvestigationBudget",
    "InvestigationLimits",
    "ModelCallTelemetry",
    "StructuredModelResult",
    "TensorMuxClient",
    "TensorMuxError",
    "TensorMuxSettings",
    "build_messages",
    "investigate_unresolved_case",
]
