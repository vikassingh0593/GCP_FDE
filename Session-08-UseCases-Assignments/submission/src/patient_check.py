"""Patient-case check (D70, D73): a classifier run by code, and any doubt goes to a person.

One small Gemini call made by CODE, never by the orchestrator, before the router sees the message,
with a fixed question (policy.PATIENT_CASE_QUESTION) answered in JSON: yes / no / unsure. It reads
meaning, so indirect wording, typos and other languages are covered (trial: 22 of 22, median 1.1 s).

Rule, fail closed: yes, unsure, or no usable answer (an error, an unreadable reply) is a patient case;
only a clear "no" is answered normally. Nothing downstream can turn a patient case back into an answer.

D73 (2026-10-20): the word patterns that ran first (D53: "my patient", an age, "should I give") were
dropped. They saved about a second on obvious cases but added no safety (the classifier catches all
they caught, and a failed call already escalates), and they were a hand-made word list.
"""

from __future__ import annotations

import hashlib
import json
import traceback

from google.genai import types

import rag_runtime as rt
import replay
from config import PATIENT_CHECK_MODEL, PATIENT_CHECK_THINKING_BUDGET, VERTEX_LOCATION
from policy import PATIENT_CASE_QUESTION

VERDICTS = ("yes", "no", "unsure")
SCHEMA = {"type": "OBJECT", "properties": {
    "patient_case": {"type": "STRING", "enum": list(VERDICTS)},
    "reason": {"type": "STRING"}}, "required": ["patient_case", "reason"]}
# Recordings are keyed by the question's text too, so editing it forces a re-recording.
QUESTION_VERSION = hashlib.sha256(PATIENT_CASE_QUESTION.encode()).hexdigest()[:12]


def decide(verdict: str) -> bool:
    """The rule in one place: anything but a clear "no" is a patient case."""
    return verdict != "no"


def classify(text: str) -> dict:
    """The classifier's verdict, recorded and replayed like every other model call."""
    key = {"text": text, "model": PATIENT_CHECK_MODEL, "thinking": PATIENT_CHECK_THINKING_BUDGET,
           "question": QUESTION_VERSION}
    return replay.call("patient_check", key, lambda: _classify_remote(text))


def _classify_remote(text: str) -> dict:
    response = rt.with_retry(lambda: rt._genai(VERTEX_LOCATION).models.generate_content(
        model=PATIENT_CHECK_MODEL, contents=PATIENT_CASE_QUESTION.replace("{message}", text),
        config=types.GenerateContentConfig(
            temperature=0, response_mime_type="application/json", response_schema=SCHEMA,
            thinking_config=types.ThinkingConfig(thinking_budget=PATIENT_CHECK_THINKING_BUDGET),
        ),
    ), "patient_check")
    return json.loads(response.text)


def check(text: str) -> dict:
    """The verdict and the decision. Never raises: no usable verdict is a patient case (fail closed)."""
    text = (text or "").strip()
    if not text:
        return {"patient_case": False, "classifier": "skipped", "reason": "no message text"}
    try:
        result = classify(text)
        verdict = result.get("patient_case") if result.get("patient_case") in VERDICTS else "error"
        reason = str(result.get("reason", ""))
    except Exception as exc:  # no verdict → a person decides
        traceback.print_exc()
        verdict, reason = "error", f"classifier failed: {type(exc).__name__}: {str(exc)[:160]}"
    return {"patient_case": decide(verdict), "classifier": verdict, "reason": reason}
