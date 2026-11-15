"""Hybrid semantic orchestrator: reason -> validate -> execute -> observe -> re-plan."""
from __future__ import annotations
from google import genai
from app.enterprise.tools import TOOL_REGISTRY
from app.orchestrator.models import EvidenceItem, OrchestrationReport, WorkflowState
from app.orchestrator.semantic import decide_next
from app.runtime.policy import OrchestrationPolicy, validate_decision

class SemanticOrchestrator:
    def __init__(self, client: genai.Client, policy: OrchestrationPolicy | None = None):
        self.client = client
        self.policy = policy or OrchestrationPolicy()

    def run(self, objective: str, ticket_id: str) -> tuple[WorkflowState, OrchestrationReport]:
        state = WorkflowState(objective=objective, ticket_id=ticket_id)
        while state.step < self.policy.max_steps:
            decision = decide_next(state, self.client)
            gate = validate_decision(state, decision, self.policy)
            if not gate.allowed:
                state.termination_reason = gate.reason
                break
            state.decisions.append(decision)
            state.step += 1
            if decision.action in {"SYNTHESIZE", "STOP"}:
                state.termination_reason = decision.action
                break
            tool = TOOL_REGISTRY[decision.action]
            args = dict(decision.arguments)
            if decision.action != "SEARCH_KNOWLEDGE":
                args.setdefault("ticket_id", ticket_id)
            try:
                result = tool(**args)
                if isinstance(result, dict) and "error" in result:
                    state.failures.append(str(result["error"]))
                else:
                    state.evidence.append(EvidenceItem(source=decision.action, payload=result))
            except Exception as exc:
                state.failures.append(f"{decision.action}:{type(exc).__name__}")
        
        
        if not state.termination_reason:
            state.termination_reason = "MAX_STEPS_REACHED"
        report = OrchestrationReport(
            objective=objective,
            steps=state.step,
            actions=[d.action for d in state.decisions],
            failures=state.failures,
            termination_reason=state.termination_reason,
            evidence_sources=[e.source for e in state.evidence],
        )
        return state, report
