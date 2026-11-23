"""Grounded final synthesis from evidence collected by the orchestrator."""
from __future__ import annotations
import json, os
from google import genai
from app.orchestrator.models import WorkflowState

MODEL_ID = os.getenv("MODEL_ID", "gemini-2.5-flash")

def synthesize(state: WorkflowState, client: genai.Client) -> str:
    evidence = [e.model_dump() for e in state.evidence]
    prompt = f"""Produce a concise enterprise support investigation result.
Use ONLY the supplied evidence. Separate finding, evidence, uncertainty, and recommended next action.
Objective: {state.objective}
Evidence: {json.dumps(evidence)}
Failures: {json.dumps(state.failures)}
"""
    return client.models.generate_content(model=MODEL_ID, contents=prompt).text
