"""Topic 4 — zero-shot, few-shot, rules/context and structured output."""
from typing import Literal
from google.genai import types
from pydantic import BaseModel
from common import generate

class TriageDecision(BaseModel):
    category: Literal["shipping", "billing", "account", "other"]
    priority: Literal["low", "medium", "high"]
    needs_human_review: bool
    next_action: str

def show(title: str, prompt: str, config=None) -> None:
    print(f"\n{'='*70}\n{title}\n{'='*70}")
    response, latency = generate(prompt, config=config)
    print(response.text)
    print(f"Latency: {latency:.2f}s")

show("1. ZERO-SHOT", """
Classify as shipping, billing, account, or other.
Return only the category.
Request: "The parcel says delivered but I do not have it."
""")

show("2. FEW-SHOT", """
Examples:
"My card was charged twice." -> billing
"I cannot reset my password." -> account
"Tracking has not changed for five days." -> shipping

Now classify:
"The parcel says delivered but I do not have it."
""")

show("3. RULES + CONTEXT", """
ROLE: You are a support-triage component.
RULES:
- Use only supplied evidence.
- Never invent a live carrier event.
- If evidence is insufficient, state that clearly.
CONTEXT:
Customer: "Order 412 is late."
Carrier data: No current carrier event.
TASK:
Is the cause of delay established?
""")

config=types.GenerateContentConfig(
    response_mime_type="application/json",
    response_schema=TriageDecision,
    temperature=0.1,
)
response, latency=generate("""
ROLE: You are a support-triage component.
TASK: Classify the request and recommend the next step.
REQUEST: "The parcel says delivered but I do not have it."
RULES:
- Do not invent live carrier information.
- Mark human review when investigation is required.
""", config=config)
decision=TriageDecision.model_validate_json(response.text)
print(f"\n{'='*70}\n4. STRUCTURED OUTPUT\n{'='*70}")
print(decision.model_dump_json(indent=2))
print(f"Latency: {latency:.2f}s")
