"""Semantic next-action planner using Gemini structured output.

The model proposes the next best action from current objective + accumulated evidence.
The deterministic control plane decides whether that proposal may execute.
"""
from __future__ import annotations
import json, os
from google import genai
from google.genai import types
from app.orchestrator.models import OrchestrationDecision, WorkflowState

MODEL_ID = os.getenv("MODEL_ID", "gemini-2.5-flash")
ALLOWED_ACTIONS = ["GET_TICKET","GET_TELEMETRY","GET_RECENT_CHANGES","SEARCH_KNOWLEDGE","VALIDATE_IDENTITY_BINDING","SYNTHESIZE","STOP"]

SYSTEM = """You are the semantic orchestrator for an enterprise support investigation.
Choose exactly ONE next action based on the objective and evidence already collected.
Do not repeat evidence collection without a clear information-gain reason.
Prefer the smallest useful next step. Use SEARCH_KNOWLEDGE with argument symptom chosen from observed symptoms.
Use VALIDATE_IDENTITY_BINDING when evidence suggests identity/credential binding issues.
Use SYNTHESIZE when evidence is sufficient to form a grounded conclusion.
Use STOP only when no useful action remains. Return structured JSON only."""

def decide_next(state: WorkflowState, client: genai.Client) -> OrchestrationDecision:
    prompt = {
        "objective": state.objective,
        "ticket_id": state.ticket_id,
        "step": state.step,
        "available_actions": ALLOWED_ACTIONS,
        "evidence": [e.model_dump() for e in state.evidence],
        "previous_decisions": [d.model_dump() for d in state.decisions],
        "failures": state.failures,
    }
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=json.dumps(prompt),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=OrchestrationDecision,
            temperature=0.1,
        ),
    )
    return OrchestrationDecision.model_validate_json(response.text)
