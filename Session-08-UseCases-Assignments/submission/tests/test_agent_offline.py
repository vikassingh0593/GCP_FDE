"""Offline tests for the agent's output callback (no Gemini, no cloud).

The callback decides in code what the user sees:
  - after a tool ran: the tool's checked answer, verbatim (D31);
  - without a tool: the model's own small talk, unless it contains a dose or
    clinical figure, which is replaced by a fixed message (D45).

Run from submission/:  pytest tests/
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ["MEDEVIDENCE_OFFLINE"] = "1"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "tredence-fde-1")
os.environ.setdefault("GCS_BUCKET", "tredence-fde-1-medevidence-vks")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "harness"))

from google.adk.models import LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402

from medevidence_agent_vks import agent  # noqa: E402  (builds its prompt from the replayed registry)
from tools import RELAY_KEY  # noqa: E402


def _reply(text: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def _shown(state: dict, text: str) -> str:
    out = agent.relay_tool_answer(SimpleNamespace(state=state), _reply(text))
    return text if out is None else out.content.parts[0].text


def test_tool_answer_is_shown_verbatim_and_model_words_dropped():
    state = {RELAY_KEY: ["25 mg OD [E1]\n\nSources ..."]}
    assert _shown(state, "In short, the dose is 50 mg.") == "25 mg OD [E1]\n\nSources ..."
    assert state[RELAY_KEY] == []  # used once


def test_several_tool_answers_are_all_shown_in_order():
    """D51: two tools in one turn → both checked answers, joined by code, no model words."""
    state = {RELAY_KEY: ["rows from text_to_sql", "answer from search_current"]}
    assert _shown(state, "Here is a summary...") == "Part 1\nrows from text_to_sql\n\nPart 2\nanswer from search_current"


def test_small_talk_without_a_number_passes_unchanged():
    for text in ("Hello, how can I help?", "I'm doing well, thanks! What would you like to know?",
                 "For which country? Germany, Singapore, UAE, United States."):
        assert _shown({}, text) == text


def test_no_tool_reply_with_a_dose_or_clinical_figure_is_replaced():
    for text in ("The usual adult dose of ibuprofen is 400 mg every 6 hours.",
                 "About 12.7% of patients had nausea.", "Stop if ALT rises above 3x ULN."):
        assert _shown({}, text) == agent.NO_TOOL_FIGURE_MESSAGE


def test_tool_call_turn_is_left_alone():
    call = LlmResponse(content=types.Content(role="model", parts=[
        types.Part(function_call=types.FunctionCall(name="search_current", args={"country": "Germany"}))]))
    assert agent.relay_tool_answer(SimpleNamespace(state={RELAY_KEY: ["x"]}), call) is None


def test_instruction_is_built_from_data_not_written_by_hand():
    """D46/D47: the catalogue, countries, product and contacts are filled in from the data."""
    import rag_runtime as rt
    assert "{" not in agent.INSTRUCTION.replace("{}", "")  # no placeholder left unfilled
    assert all(doc_id in agent.INSTRUCTION for doc_id in rt.registry())
    assert ", ".join(rt.covered_countries()) in agent.INSTRUCTION


def test_tool_calls_are_capped_per_turn_and_repeats_skipped():
    """D51: the cap is enforced in code, not by the prompt."""
    ctx = SimpleNamespace(state={})
    agent.start_turn(ctx)
    search = SimpleNamespace(name="search_current")
    assert agent.limit_tool_calls(search, {"question": "a", "country": "Germany"}, ctx) is None
    assert agent.limit_tool_calls(search, {"question": "a", "country": "Germany"}, ctx)["outcome"] == "skipped"
    for i in range(agent.MAX_TOOL_CALLS_PER_TURN - 1):
        assert agent.limit_tool_calls(search, {"question": f"b{i}", "country": "Germany"}, ctx) is None
    assert agent.limit_tool_calls(search, {"question": "one too many", "country": "Germany"}, ctx)["outcome"] == "skipped"
    agent.start_turn(ctx)  # a new user message resets the count
    assert agent.limit_tool_calls(search, {"question": "a", "country": "Germany"}, ctx) is None


# Step 7: patient cases always reach a person (D53); no-tool medical words (D56)

def _turn(text: str) -> SimpleNamespace:
    ctx = SimpleNamespace(state={}, user_content=types.Content(role="user", parts=[types.Part(text=text)]))
    agent.start_turn(ctx)
    return ctx


def test_patient_patterns_separate_individual_cases_from_information():
    for text in ("My 70-year-old patient has eGFR 35 and ALT 4x ULN. What dose should I give him?",
                 "Should I increase the dose?", "He has eGFR 28, what now?"):
        assert agent.is_patient_case(text), text
    for text in ("What does the label say for eGFR 30-59?", "Which patients need hepatic monitoring?",
                 "What is the current renal starting dose for patients with moderate impairment in Germany?"):
        assert not agent.is_patient_case(text), text


def test_patient_case_skips_every_tool_except_escalate():
    ctx = _turn("My 70-year-old patient has eGFR 35. What dose should I give him?")
    assert agent.limit_tool_calls(SimpleNamespace(name="search_current"), {"question": "dose"}, ctx)["outcome"] == "skipped"
    assert agent.limit_tool_calls(SimpleNamespace(name="escalate"), {"reason": "patient_specific"}, ctx) is None


def test_patient_case_the_model_missed_is_escalated_by_code():
    """Layer 3: no escalate call this turn → code makes the hand-off (offline: a local record)."""
    ctx = _turn("Should I increase her dose? Her eGFR is 40.")
    shown = agent.relay_tool_answer(ctx, _reply("For eGFR 40 the starting dose is lower.")).content.parts[0].text
    assert "Individual treatment decisions" in shown and "ESC-" in shown and "eGFR 40" not in shown


def test_no_tool_reply_with_clinical_words_from_memory_is_replaced():
    ctx = _turn("What is AX-17?")
    assert _shown(ctx.state, "AX-17 is a kinase inhibitor used to treat cancer.") == agent.NO_TOOL_MEDICAL_MESSAGE
    catalogue_answer = "AX-17 is the product these documents cover; e.g. Table 3. Renal dose modification."
    assert _shown(ctx.state, catalogue_answer) == catalogue_answer
