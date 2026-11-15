"""Production-shaped semantic orchestration loop."""

from __future__ import annotations
import os, time, uuid
from app.contracts import Action
from app.evidence import EvidenceRegister
from app.policy import RuntimePolicy, READ_ACTIONS
from app.semantic import SemanticOrchestrator
from app.synthesis import synthesize
from app.tools import execute


class Investigation:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        self.correlation_id = f"CORR-{uuid.uuid4().hex[:10]}"
        self.evidence = EvidenceRegister()
        self.policy = RuntimePolicy()
        self.semantic = SemanticOrchestrator()
        self.trajectory: list[dict] = []
        self.tool_calls = 0
        self.max_steps = int(os.getenv("MAX_STEPS", "8"))
        self.deadline = time.monotonic() + int(os.getenv("MAX_ELAPSED_SECONDS", "45"))

    def run(self):
        for step in range(1, self.max_steps + 1):
            if time.monotonic() > self.deadline:
                return self._terminal("TIMEOUT_TERMINATION")

            decision = self.semantic.decide(
                self.order_id, self.evidence, self.trajectory
            )
            policy = self.policy.evaluate(
                decision, self.evidence, self.tool_calls
            )

            event = {
                "step": step,
                "decision_id": f"DEC-{uuid.uuid4().hex[:8]}",
                "proposed_action": decision.next_action.value,
                "reason": decision.reason,
                "policy": "ALLOW" if policy.allowed else "REJECT",
                "policy_reason": policy.reason,
            }
            self.trajectory.append(event)
            self._print_event(event)

            if not policy.allowed:
                # A rejected semantic proposal is visible and bounded.
                # Gemini receives this trajectory on the next step and can re-plan.
                continue

            if decision.next_action in READ_ACTIONS:
                status, source, payload, timestamp = execute(
                    decision.next_action, self.order_id
                )
                item = self.evidence.add(
                    decision.next_action.value,
                    source,
                    status,
                    payload,
                    timestamp,
                )
                self.tool_calls += 1
                event["evidence_id"] = item.evidence_id
                event["tool_status"] = status
                print(f"EVIDENCE : {item.evidence_id} ({status})\n")
                continue

            if decision.next_action == Action.SYNTHESIZE:
                result = synthesize(self.order_id, self.evidence)
                print("\n=== GROUNDED OUTCOME ===")
                print(result.model_dump_json(indent=2))
                return result

            if decision.next_action == Action.ESCALATE:
                return self._terminal("ESCALATED")

            if decision.next_action == Action.STOP_INSUFFICIENT_EVIDENCE:
                return self._terminal("INSUFFICIENT_EVIDENCE")

        return self._terminal("MAX_STEPS_EXCEEDED")

    def _terminal(self, reason: str):
        print(f"\nTERMINATED: {reason}")
        print(f"Correlation ID: {self.correlation_id}")
        return {"termination_reason": reason, "evidence": self.evidence.prompt_view()}

    @staticmethod
    def _print_event(event: dict) -> None:
        print(f"\nSTEP {event['step']}")
        print(f"PROPOSED : {event['proposed_action']}")
        print(f"REASON   : {event['reason']}")
        print(f"POLICY   : {event['policy']} — {event['policy_reason']}")
