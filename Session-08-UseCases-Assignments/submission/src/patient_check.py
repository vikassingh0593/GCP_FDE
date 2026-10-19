"""Patient-case check (D70, external review Priority 2): two signals, and doubt goes to a person.

Signal 1, the word patterns (policy.PATIENT_PATTERNS, D53): fast, free and deterministic, but they
miss unusual wording (review test: 5 of 8 reworded patient questions).
Signal 2, a classifier: one small Gemini call made by CODE, never by the orchestrator, with a fixed
question (policy.PATIENT_CASE_QUESTION) and a JSON answer: yes / no / unsure. It reads meaning, so
indirect wording, typos and other languages are covered (trial: 22 of 22, median 1.1 s).

Rule, fail closed: a patient case when the patterns match, OR the classifier says yes or unsure, OR
the classifier gives no usable answer (an error, an unreadable reply). Only "patterns: no and
classifier: no" is answered normally. The classifier can add a patient flag, never remove one, so
when the patterns already match it is not called: the outcome could not change.
"""

from __future__ import annotations

import hashlib
import json
import traceback

from google.genai import types

import rag_runtime as rt
import replay
from config import PATIENT_CHECK_MODEL, PATIENT_CHECK_THINKING_BUDGET, VERTEX_LOCATION
from policy import PATIENT_CASE_QUESTION, PATIENT_PATTERNS

VERDICTS = ("yes", "no", "unsure")
SCHEMA = {"type": "OBJECT", "properties": {
    "patient_case": {"type": "STRING", "enum": list(VERDICTS)},
    "reason": {"type": "STRING"}}, "required": ["patient_case", "reason"]}
# Recordings are keyed by the question's text too, so editing it forces a re-recording.
QUESTION_VERSION = hashlib.sha256(PATIENT_CASE_QUESTION.encode()).hexdigest()[:12]


def patterns_match(text: str) -> bool:
    """Signal 1 (D53): the word patterns."""
    return any(p.search(text or "") for p in PATIENT_PATTERNS)


def decide(patterns: bool, verdict: str) -> bool:
    """The rule in one place: either signal, or any doubt, makes it a patient case."""
    return patterns or verdict != "no"


def classify(text: str) -> dict:
    """Signal 2: the classifier's verdict, recorded and replayed like every other model call."""
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
    """Both signals and the decision. Never raises: no usable verdict is a patient case (fail closed)."""
    text = (text or "").strip()
    if not text:
        return {"patient_case": False, "patterns": False, "classifier": "skipped", "reason": "no message text"}
    if patterns_match(text):
        return {"patient_case": True, "patterns": True, "classifier": "skipped", "reason": "word patterns matched"}
    try:
        result = classify(text)
        verdict = result.get("patient_case") if result.get("patient_case") in VERDICTS else "error"
        reason = str(result.get("reason", ""))
    except Exception as exc:  # no verdict → a person decides
        traceback.print_exc()
        verdict, reason = "error", f"classifier failed: {type(exc).__name__}: {str(exc)[:160]}"
    return {"patient_case": decide(False, verdict), "patterns": False, "classifier": verdict, "reason": reason}
