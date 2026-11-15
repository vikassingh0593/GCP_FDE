"""Gemini semantic decision layer."""

from __future__ import annotations
import json, os
from google import genai
from google.genai import types
from app.contracts import NextAction
from app.evidence import EvidenceRegister

SYSTEM = """You are the semantic orchestration brain for an enterprise order
exception investigation.

Choose exactly ONE next action.

You may only choose from:
GET_ORDER, CHECK_INVENTORY, CHECK_PAYMENT_HOLD, CHECK_WAREHOUSE,
GET_CARRIER_STATUS, GET_RECENT_CHANGES, SEARCH_OPERATIONS_KNOWLEDGE,
SYNTHESIZE, STOP_INSUFFICIENT_EVIDENCE, ESCALATE.

Optimize for information value and avoid unnecessary calls.
Do not assume historical similarity proves current causality.
Do not treat model confidence as evidence.
SYNTHESIZE only when evidence is sufficient for a grounded operational result.
The deterministic runtime, not you, has final authority over execution.
"""

class SemanticOrchestrator:
    def __init__(self) -> None:
        self.client = genai.Client(
            vertexai=True,
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        )
        self.model = os.getenv("MODEL_ID", "gemini-2.5-flash")

    def decide(
        self,
        order_id: str,
        evidence: EvidenceRegister,
        trajectory: list[dict],
    ) -> NextAction:
        prompt = {
            "objective": f"Diagnose order exception {order_id}.",
            "evidence": evidence.prompt_view(),
            "trajectory": trajectory,
        }
        response = self.client.models.generate_content(
            model=self.model,
            contents=json.dumps(prompt, default=str),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM,
                response_mime_type="application/json",
                response_schema=NextAction,
                temperature=0.1,
            ),
        )
        return NextAction.model_validate_json(response.text)
