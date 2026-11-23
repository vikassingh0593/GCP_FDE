"""Deterministic control plane. Gemini cannot override these rules."""

from __future__ import annotations
import os
from app.contracts import Action, NextAction, PolicyDecision
from app.evidence import EvidenceRegister


READ_ACTIONS = {
    Action.GET_ORDER,
    Action.CHECK_INVENTORY,
    Action.CHECK_PAYMENT_HOLD,
    Action.CHECK_WAREHOUSE,
    Action.GET_CARRIER_STATUS,
    Action.GET_RECENT_CHANGES,
    Action.SEARCH_OPERATIONS_KNOWLEDGE,
}

TERMINAL_ACTIONS = {
    Action.SYNTHESIZE,
    Action.STOP_INSUFFICIENT_EVIDENCE,
    Action.ESCALATE,
}


class RuntimePolicy:
    def __init__(self) -> None:
        self.max_tool_calls = int(os.getenv("MAX_TOOL_CALLS", "7"))
        self.max_same_action = int(os.getenv("MAX_SAME_ACTION_CALLS", "2"))

    def evaluate(
        self,
        decision: NextAction,
        evidence: EvidenceRegister,
        tool_calls: int,
    ) -> PolicyDecision:
        action = decision.next_action

        if action in READ_ACTIONS:
            if tool_calls >= self.max_tool_calls:
                return PolicyDecision(
                    allowed=False,
                    reason="Tool-call budget exhausted.",
                )
            if evidence.action_count(action.value) >= self.max_same_action:
                return PolicyDecision(
                    allowed=False,
                    reason=f"Repeated-action limit reached for {action.value}.",
                )
            return PolicyDecision(allowed=True, reason="Permitted read action.")

        if action == Action.SYNTHESIZE:
            successful = evidence.successful_actions()
            if Action.GET_ORDER.value not in successful:
                return PolicyDecision(
                    allowed=False,
                    reason="Synthesis requires authoritative order evidence.",
                )
            cause_specific = successful.intersection(
                {
                    Action.CHECK_INVENTORY.value,
                    Action.CHECK_PAYMENT_HOLD.value,
                    Action.CHECK_WAREHOUSE.value,
                    Action.GET_CARRIER_STATUS.value,
                    Action.GET_RECENT_CHANGES.value,
                }
            )
            if not cause_specific:
                return PolicyDecision(
                    allowed=False,
                    reason="Synthesis requires at least one cause-specific evidence source.",
                )
            return PolicyDecision(allowed=True, reason="Minimum synthesis evidence satisfied.")

        if action in {Action.STOP_INSUFFICIENT_EVIDENCE, Action.ESCALATE}:
            return PolicyDecision(allowed=True, reason="Safe terminal action.")

        return PolicyDecision(allowed=False, reason="Action is not permitted.")
