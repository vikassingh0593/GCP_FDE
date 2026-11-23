"""Grounded final synthesis using the evidence register."""

from __future__ import annotations
import json, os
from google import genai
from google.genai import types
from app.contracts import FinalOutcome
from app.evidence import EvidenceRegister

SYSTEM = """Create a grounded operational conclusion from ONLY the supplied
evidence. Cite evidence IDs. Distinguish observation from inference. Never
claim that temporal correlation proves causality. Surface missing or
contradictory evidence. Prefer human review for unresolved/high-impact cases."""

def synthesize(order_id: str, evidence: EvidenceRegister) -> FinalOutcome:
    client = genai.Client(
        vertexai=True,
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
    )
    response = client.models.generate_content(
        model=os.getenv("MODEL_ID", "gemini-2.5-flash"),
        contents=json.dumps(evidence.prompt_view(), default=str),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=FinalOutcome,
            temperature=0.1,
        ),
    )
    result = FinalOutcome.model_validate_json(response.text)
    if result.order_id != order_id:
        result.order_id = order_id
    return result
