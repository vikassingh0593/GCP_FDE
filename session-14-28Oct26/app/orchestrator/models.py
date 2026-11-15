"""Structured contracts separating semantic reasoning from deterministic execution."""
from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

Action = Literal["GET_TICKET","GET_TELEMETRY","GET_RECENT_CHANGES","SEARCH_KNOWLEDGE","VALIDATE_IDENTITY_BINDING","SYNTHESIZE","STOP"]

class OrchestrationDecision(BaseModel):
    action: Action
    reason: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    expected_information_gain: str = ""
    confidence: float = Field(ge=0.0, le=1.0)

class EvidenceItem(BaseModel):
    source: str
    payload: dict[str, Any]

class WorkflowState(BaseModel):
    objective: str
    ticket_id: str
    step: int = 0
    evidence: list[EvidenceItem] = Field(default_factory=list)
    decisions: list[OrchestrationDecision] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    termination_reason: str | None = None

class OrchestrationReport(BaseModel):
    objective: str
    steps: int
    actions: list[str]
    failures: list[str]
    termination_reason: str
    evidence_sources: list[str]
