"""MedEvidence agent, v3 (Step 6): one ADK root agent with five tools.

The agent UNDERSTANDS the question: its class (§4), whether a country or a
date is known, whether to ask back, which tool to call. It never decides
status, country rules or legal effect; those live in the runtime and the tools
(architecture.md §9). The tools are plain functions with fixed pipelines, not
sub-agents: nothing inside them needs a model to decide (§9, Step 5 review).

Run locally only (never deployed, by decision):
    cd submission && source .venv/bin/activate && source env.sh
    cd harness && adk web          # then choose medevidence_agent_vks

v5 scope: search_current, search_historical, lookup_document, compare_studies,
escalate (function tools) and sql_analyst, a specialist agent called as a tool
(D67: write → check → repair loop; the orchestrator keeps the conversation, D68). Open small talk without a tool, checked
in code (D45: no clinical figure; D56: no clinical word that is not in the
catalogue or the question); several tools per turn, capped in code (D51);
patient cases always reach a person, by three layers (D53).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HARNESS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS))
sys.path.insert(0, str(HARNESS.parent / "src"))

from google.adk.agents import Agent  # noqa: E402
from google.adk.agents.callback_context import CallbackContext  # noqa: E402
from google.adk.models import LlmResponse  # noqa: E402
from google.adk.models.google_llm import Gemini  # noqa: E402
from google.genai import types  # noqa: E402

from config import AGENT_MODEL, ASSISTANT_NAME, MAX_TOOL_CALLS_PER_TURN, ORGANISATION  # noqa: E402
from policy import CLINICAL_FIGURE, CLINICAL_TERMS, HANDOFF, PATIENT_PATTERNS  # noqa: E402
import escalation  # noqa: E402
import rag_runtime as rt  # noqa: E402
from tools import (ESCALATED_KEY, RELAY_KEY, TRACE, compare_studies, escalate, lookup_document,  # noqa: E402
                   search_current, search_historical, start_turn_state)
from sql_agent import SQL_RELAY_KEY, sql_analyst_tool  # noqa: E402  (specialist agent, D67)


INSTRUCTION_TEMPLATE = """
You are {assistant}, the assistant of {organisation}. You answer questions about the products in the
controlled documents ONLY from those documents: through your tools, or from the CATALOGUE at the end
of this instruction. You never answer a medical question from your own knowledge.

Decide what kind of question it is, then act:

1. CONVERSATION, NO TOOL: reply naturally and briefly yourself to
   - greetings, thanks, "how are you?" (do not list your scope unless asked);
   - questions about you and how to use you: what you can do (current and earlier guidance by
     country, specific documents and their tables, always with sources), how to phrase a question,
     what "current" and "historical" mean, what the Sources links are;
   - light non-medical chat (a joke, a general non-medical question).
   NEVER answer from your own knowledge anything about a medicine, dose, side effect, interaction,
   lab value, disease or treatment, including general medical knowledge and any product that is not
   in the CATALOGUE: say you only answer clinical questions from the controlled documents and name
   the products in the CATALOGUE. Never write a dose, a percentage or any clinical number in your
   own words.

2. THE COLLECTION ITSELF, NO TOOL: "what is <product>?", "what documents do you have?", "which
   countries?", and vague requests without a specific question ("tell me something about it",
   "show for <country>", "anything for <country>"). Answer ONLY from the CATALOGUE: the product is
   the one these controlled documents cover; say which documents, countries, versions, dates and
   tables exist (for a country: its local documents AND always the GLOBAL ones, which apply to every
   country as supporting evidence). The CATALOGUE does not
   say what a medicine is, does or treats, so never describe that. End with one or two questions
   the user could ask, built from the table titles. Never send a vague request to a search tool.

3. A DOCUMENT ID IS NAMED (an ID from the CATALOGUE, or one shaped like them): call lookup_document.
   - The user wants a table from it: put their words in `table` ("Table 2", "the dosing table") and
     any row labels they named in `rows`. Never invent a table name.
   - The user asks something about its content: put the question in `question`.
   - Only the ID ("what is <ID>?"): leave table, rows and question empty.
   A follow-up that names a table or rows refers to the document of the previous turn. A table
   request WITHOUT a document ID: ask "Which document?" and list the CATALOGUE documents that have
   tables.

4. CURRENT GUIDANCE WITH A NAMED COUNTRY (what applies now): call search_current with the user's
   question, the country, and the product ("" unless the user named one). This applies to ANY
   country the user names, EVEN WHEN THE CATALOGUE SHOWS IT IS NOT COVERED: never answer a coverage
   question yourself; the tool gives the approved reply, offers the hand-off and logs it. Use
   the country from earlier in the conversation if the user already gave one. A follow-up with only
   a new country ("and in <country>?", "show for <country>") repeats the previous question for that
   country only if the previous question was a specific one; otherwise it is a vague request (2).

5. EARLIER GUIDANCE WITH A NAMED COUNTRY: call search_historical (product as in 4).
   - A time point is given: put it in `as_of` as YYYY-MM-DD. A full date → that date; a month →
     its last day ("March 2021" → 2021-03-31); a year → 31 December ("in 2020" → 2020-12-31).
   - "What changed", "the previous / earlier / superseded version", "before the latest revision":
     as_of = "" (all versions, earlier ones marked HISTORICAL).
   - Past tense with NO time point and no version wording ("what was the dose in <country>?"): do
     not call a tool; ask "As of which date? Or should I show what changed between versions?"

6. NO COUNTRY NAMED for 4 or 5: ask "For which country?" and list the covered ones: {covered}.
   Never guess a country. If the user DID name any country (covered or not, e.g. one missing from
   that list), never ask for the country: call the tool with it; the tool answers "not covered".

7. COMPARING STUDIES ("compare <study> and <study>", "how do the studies differ on <event>?"): call
   compare_studies with the study IDs, the event if one is named (else ""), and the question. Call it
   whenever the user asks to compare documents by ID, even if one may not be a study: the tool checks
   and lists the real studies. A
   question that mixes study numbers with what the studies say about them also goes to
   compare_studies alone (it has both the rows and the study tables).

8. COUNTS, RANKINGS, TOTALS OR LISTS FROM THE DATA ("which study had the highest rash rate?",
   "how many approved documents per country?", "list the superseded documents"): call
   sql_analyst with the user's question as the request (a specialist agent that writes, checks and,
   if needed, repairs the SQL). Use it even when the CATALOGUE seems to hold the answer, so
   numbers are counted by the database, never by you. A request to change, delete or drop data:
   do not call a tool; say you can only read the controlled documents.

9. A QUESTION WITH SEVERAL PARTS that need different tools: call one tool per part, at most
   {max_calls} in total; every checked answer is shown in order. Never call the same tool twice
   with the same arguments.

10. ONE SPECIFIC PATIENT (their age, personal lab values, "my patient", "should I give him/her"): never
   give individual advice and call no other tool. Call escalate with reason "patient_specific", the
   question, a general_question (the same question with every patient detail removed, e.g. "renal
   dosing guidance for moderate impairment and hepatic monitoring") and the country if known
   (else ""). Drop the patient's values but keep the topics they point to (a liver value → hepatic
   monitoring and its thresholds). Its reply hands the case to {medical} and shows general
   reference only. A question that only states or assumes a general value ("so severe must be
   12.5 mg?") with no specific person is NOT a patient case: it goes to search_current.

11. "ROUTE IT", "YES, ESCALATE", "PASS IT ON" after an answer that said it could not help: call
   escalate with reason "user_request", the earlier question, general_question "" and its country.

After a tool returns, its checked answer is shown to the user exactly as returned.
Do not add facts, numbers or advice of your own.

CATALOGUE (built from the document registry when you started; the only facts about the collection
you may state without a tool):
{catalogue}
"""

# Everything about the collection is read from the data when the agent starts
# (D44, D46, D47): products, countries, documents and their tables come from the
# registry and the chunks table; names and contacts from env.sh and policy.py.
# A new product, country or document reaches the prompt with no code edit
# (restart adk web after an ingestion run).
INSTRUCTION = (INSTRUCTION_TEMPLATE
               .replace("{assistant}", ASSISTANT_NAME)
               .replace("{organisation}", ORGANISATION)
               .replace("{covered}", ", ".join(rt.covered_countries()))
               .replace("{medical}", HANDOFF["medical"])
               .replace("{max_calls}", str(MAX_TOOL_CALLS_PER_TURN))
               .replace("{catalogue}", rt.catalogue()))


# D56: clinical words a no-tool reply may use: those in the catalogue (built from data) or the question.
CATALOGUE_WORDS = set(re.findall(r"[a-z][a-z\-]+", rt.catalogue().lower()))
NO_TOOL_MEDICAL_MESSAGE = ("I can only give medical information from the controlled documents, with sources. "
                           "Ask me about a country or a document ID, or say \"route it\" and I'll pass the question "
                           f"to {HANDOFF['medical']}.")


def unsupported_clinical_terms(reply: str, question: str) -> list[str]:
    """D56: clinical words in a no-tool reply that neither the catalogue nor the user's question contains."""
    allowed = CATALOGUE_WORDS | set(re.findall(r"[a-z][a-z\-]+", (question or "").lower()))
    return sorted({w for w in re.findall(r"[a-z][a-z\-]+", reply.lower()) if w in CLINICAL_TERMS and w not in allowed})


# D45: shown instead of a no-tool reply that contains a dose or clinical figure.
NO_TOOL_FIGURE_MESSAGE = ("I can only give doses and clinical figures from the controlled documents, with sources. "
                          "Ask me about a country or a document ID, or I can route the question to "
                          f"{HANDOFF['medical']}.")


def relay_tool_answer(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """What the user sees, decided in code.

    After a tool answered (D31): its checked answer, verbatim. Whatever wording the
    model produced after the tool call is replaced, so no number can change after
    the citation and number checks ran.

    Without a tool (D45, small talk is open): the model's own reply, unless it
    contains a dose or clinical figure (D45) or a clinical word that is neither in
    the catalogue nor in the question (D56); then a fixed message replaces it.

    A patient case that did not reach escalate (D53, layer 3): code makes the
    hand-off itself, so the case reaches a person even if the model missed it.
    """
    content = llm_response.content
    if not content or not content.parts:
        return None
    if any(p.function_call for p in content.parts):
        return None  # the model is calling a tool, not answering yet
    own_text = " ".join(p.text for p in content.parts if p.text and not getattr(p, "thought", False))
    if not own_text:
        return None
    # Function tools relay under RELAY_KEY, the SQL specialist under its own key (an AgentTool runs on a
    # copy of the state, so one shared list could lose a part when tools run in parallel). Order: as called.
    relay = list(callback_context.state.get(RELAY_KEY) or [])
    sql_parts = list(callback_context.state.get(SQL_RELAY_KEY) or [])
    if sql_parts:
        calls = callback_context.state.get(CALLS_KEY) or []
        relay = sql_parts + relay if calls and calls[0].startswith("sql_analyst:") else relay + sql_parts
    if relay:
        callback_context.state[RELAY_KEY] = []
        callback_context.state[SQL_RELAY_KEY] = []
        # D51: several tools in one turn → every checked answer, in order, joined by code.
        text = relay[0] if len(relay) == 1 else "\n\n".join(f"Part {i}\n{part}" for i, part in enumerate(relay, 1))
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
    if callback_context.state.get(PATIENT_KEY) and not callback_context.state.get(ESCALATED_KEY):
        callback_context.state[ESCALATED_KEY] = True
        result = escalation.escalate("patient_specific", callback_context.state.get(USER_TEXT_KEY) or own_text,
                                     caller="agent:patient_precheck")
        TRACE.append({"call_id": None, "tool": "escalate(code pre-check)", "result": result})  # visible to scripts
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=result["answer"])]))
    if CLINICAL_FIGURE.search(own_text):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=NO_TOOL_FIGURE_MESSAGE)]))
    if unsupported_clinical_terms(own_text, callback_context.state.get(USER_TEXT_KEY, "")):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=NO_TOOL_MEDICAL_MESSAGE)]))
    return None


CALLS_KEY = "tool_calls_this_turn"
PATIENT_KEY = "patient_case_this_turn"
USER_TEXT_KEY = "user_text_this_turn"


def is_patient_case(text: str) -> bool:
    """D53, layer 2: code recognises a question about one specific patient (policy.PATIENT_PATTERNS)."""
    return any(p.search(text or "") for p in PATIENT_PATTERNS)


def start_turn(callback_context: CallbackContext) -> None:
    """Each user message starts a new turn: no relayed answers and no tool calls yet; and code
    decides here, before the model, whether this is a patient case (D53)."""
    content = getattr(callback_context, "user_content", None)
    text = " ".join(p.text for p in (content.parts if content and content.parts else []) if p.text)
    callback_context.state[RELAY_KEY] = []
    callback_context.state[SQL_RELAY_KEY] = []
    callback_context.state[CALLS_KEY] = []
    callback_context.state[USER_TEXT_KEY] = text
    callback_context.state[PATIENT_KEY] = is_patient_case(text)
    callback_context.state[ESCALATED_KEY] = False
    start_turn_state(callback_context.state)  # D40: the jurisdiction note compares with the previous turn only


def limit_tool_calls(tool, args: dict, tool_context) -> dict | None:
    """D51: at most MAX_TOOL_CALLS_PER_TURN tool calls per turn, and no identical repeat.

    Why in code: a model can loop (search again with the same words) or fan out
    into many searches; each call is a full pipeline (10-39 s today) and Gemini
    cost. The prompt asks for restraint; this callback enforces it. Returning a
    dict skips the tool and hands that dict to the model as the tool's result.

    Future: raise MAX_TOOL_CALLS_PER_TURN (env.sh) when questions routinely need
    more parts, e.g. after Step 7 adds escalate or when search gets faster; keep
    the repeat check, which costs nothing and only stops wasted calls.
    """
    # D53, layer 2: in a patient case only the hand-off may run; any search or SQL is skipped,
    # so no dose can be produced for an individual even if the model tries.
    if tool_context.state.get(PATIENT_KEY) and tool.name != "escalate":
        return {"outcome": "skipped", "answer": "", "reason": "patient-specific question: call escalate with "
                                                              "reason patient_specific instead"}
    calls = list(tool_context.state.get(CALLS_KEY) or [])
    signature = f"{tool.name}:{json.dumps(args, sort_keys=True, default=str)}"
    if signature in calls:
        return {"outcome": "skipped", "answer": "", "reason": "the same call was already made this turn; "
                                                              "its answer will be shown"}
    if len(calls) >= MAX_TOOL_CALLS_PER_TURN:
        return {"outcome": "skipped", "answer": "", "reason": f"limit of {MAX_TOOL_CALLS_PER_TURN} tool calls per "
                                                              "turn reached; answer with what you have"}
    tool_context.state[CALLS_KEY] = calls + [signature]
    return None


# The agent's own Gemini calls (routing) retry "busy" answers like the runtime does:
# 5 attempts, 2 s doubling to 16 s, only for 429 / 503 (shared-project rate limits).
AGENT_LLM = Gemini(
    model=AGENT_MODEL,
    retry_options=types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=16.0, exp_base=2.0,
                                         http_status_codes=[429, 503]),
)


def busy_fallback(callback_context: CallbackContext, llm_request, error: Exception) -> LlmResponse | None:
    """Still busy after the retries: a polite message instead of a crash."""
    if any(s in str(error) for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(
            text="The assistant is busy right now (Google Cloud rate limit). Please try again in a minute.")]))
    return None  # any other error is a real problem and must surface


root_agent = Agent(
    name="medevidence_agent_vks",
    model=AGENT_LLM,
    description=f"{ASSISTANT_NAME}: answers {ORGANISATION} questions about current and earlier product guidance, "
                "specific documents, study comparisons and counts, from controlled documents, with sources.",
    instruction=INSTRUCTION,
    # Five function tools (fixed pipelines) + one specialist agent where a reasoning loop is needed (D67, D68).
    tools=[search_current, search_historical, lookup_document, compare_studies, sql_analyst_tool, escalate],
    # Thinking stays on (model default); temperature 0 so the same question routes the same way.
    generate_content_config=types.GenerateContentConfig(temperature=0),
    before_agent_callback=start_turn,
    before_tool_callback=limit_tool_calls,
    after_model_callback=relay_tool_answer,
    on_model_error_callback=busy_fallback,
)
