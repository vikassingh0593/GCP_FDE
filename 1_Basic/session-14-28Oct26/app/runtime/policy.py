"""Deterministic control plane for semantic orchestration decisions."""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from app.orchestrator.models import OrchestrationDecision, WorkflowState

@dataclass(frozen=True)
class OrchestrationPolicy:
    max_steps: int = 6
    max_tool_calls: int = 8
    max_same_action: int = 2
    max_failures: int = 2
    min_stop_confidence: float = 0.78

class PolicyDecision:
    def __init__(self, allowed: bool, reason: str):
        self.allowed = allowed
        self.reason = reason

def validate_decision(state: WorkflowState, decision: OrchestrationDecision, policy: OrchestrationPolicy) -> PolicyDecision:
    if state.step >= policy.max_steps:
        return PolicyDecision(False, "MAX_STEPS_EXCEEDED")
    tool_actions = [d.action for d in state.decisions if d.action not in {"SYNTHESIZE", "STOP"}]
    if len(tool_actions) >= policy.max_tool_calls and decision.action not in {"SYNTHESIZE", "STOP"}:
        return PolicyDecision(False, "TOOL_BUDGET_EXCEEDED")
    counts = Counter(tool_actions)
    if decision.action not in {"SYNTHESIZE", "STOP"} and counts[decision.action] >= policy.max_same_action:
        return PolicyDecision(False, "REPEATED_ACTION_BLOCKED")
    if len(state.failures) >= policy.max_failures:
        return PolicyDecision(False, "FAILURE_BUDGET_EXCEEDED")
    if decision.action == "STOP" and decision.confidence < policy.min_stop_confidence:
        return PolicyDecision(False, "STOP_CONFIDENCE_TOO_LOW")
    return PolicyDecision(True, "ALLOWED")
