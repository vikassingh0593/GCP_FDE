"""Structured contracts crossing the semantic/deterministic boundary."""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class Action(str, Enum):
    GET_ORDER = "GET_ORDER"
    CHECK_INVENTORY = "CHECK_INVENTORY"
    CHECK_PAYMENT_HOLD = "CHECK_PAYMENT_HOLD"
    CHECK_WAREHOUSE = "CHECK_WAREHOUSE"
    GET_CARRIER_STATUS = "GET_CARRIER_STATUS"
    GET_RECENT_CHANGES = "GET_RECENT_CHANGES"
    SEARCH_OPERATIONS_KNOWLEDGE = "SEARCH_OPERATIONS_KNOWLEDGE"
    SYNTHESIZE = "SYNTHESIZE"
    STOP_INSUFFICIENT_EVIDENCE = "STOP_INSUFFICIENT_EVIDENCE"
    ESCALATE = "ESCALATE"


class NextAction(BaseModel):
    """Machine-validatable proposal produced by the semantic orchestrator."""

    next_action: Action
    reason: str = Field(min_length=1)
    evidence_used: list[str] = Field(default_factory=list)
    expected_information_gain: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    stop_ready: bool = False


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str


class FinalOutcome(BaseModel):
    order_id: str
    classification: str
    probable_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str]
    contradictory_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    recommended_action: str
    human_review_required: bool
    termination_reason: str
