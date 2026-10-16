"""MedEvidence agent, v3 (Step 6): one ADK root agent with five tools.

The agent UNDERSTANDS the question: its class (§4), whether a country or a
date is known, whether to ask back, which tool to call. It never decides
status, country rules or legal effect; those live in the runtime and the tools
(architecture.md §9). The tools are plain functions with fixed pipelines, not
sub-agents: nothing inside them needs a model to decide (§9, Step 5 review).

Run locally only (never deployed, by decision):
    cd submission && source .venv/bin/activate && source env.sh
    cd harness && adk web          # then choose medevidence_agent_vks

v3 scope: search_current, search_historical, lookup_document, compare_studies,
text_to_sql; open small talk without a tool (D45: never a clinical number in its
own words, checked in code); several tools per turn for multi-part questions,
capped in code (D51). Patient cases are declined until escalate arrives (Step 7).
"""

from __future__ import annotations

import json
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
from policy import CLINICAL_FIGURE, HANDOFF  # noqa: E402
import rag_runtime as rt  # noqa: E402
from tools import (RELAY_KEY, compare_studies, lookup_document, search_current, search_historical,  # noqa: E402
                   text_to_sql)


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
   Never guess a country.

7. COMPARING STUDIES ("compare <study> and <study>", "how do the studies differ on <event>?"): call
   compare_studies with the study IDs, the event if one is named (else ""), and the question. A
   question that mixes study numbers with what the studies say about them also goes to
   compare_studies alone (it has both the rows and the study tables).

8. COUNTS, RANKINGS, TOTALS OR LISTS FROM THE DATA ("which study had the highest rash rate?",
   "how many approved documents per country?", "list the superseded documents"): call
   text_to_sql with the question. Use it even when the CATALOGUE seems to hold the answer, so
   numbers are counted by the database, never by you. A request to change, delete or drop data:
   do not call a tool; say you can only read the controlled documents.

9. A QUESTION WITH SEVERAL PARTS that need different tools: call one tool per part, at most
   {max_calls} in total; every checked answer is shown in order. Never call the same tool twice
   with the same arguments.

10. ONE SPECIFIC PATIENT (their age, lab values, "my patient", "should I give him/her"): do not give
   individual dosing advice and do not call a tool. Reply that individual treatment decisions are
   for the treating physician and that the question will be routed to {medical}.

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
    contains a dose or clinical figure; then a fixed message replaces it.
    """
    content = llm_response.content
    if not content or not content.parts:
        return None
    if any(p.function_call for p in content.parts):
        return None  # the model is calling a tool, not answering yet
    own_text = " ".join(p.text for p in content.parts if p.text and not getattr(p, "thought", False))
    if not own_text:
        return None
    relay = callback_context.state.get(RELAY_KEY) or []
    if relay:
        callback_context.state[RELAY_KEY] = []
        # D51: several tools in one turn → every checked answer, in order, joined by code.
        text = relay[0] if len(relay) == 1 else "\n\n".join(f"Part {i}\n{part}" for i, part in enumerate(relay, 1))
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
    if CLINICAL_FIGURE.search(own_text):
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=NO_TOOL_FIGURE_MESSAGE)]))
    return None


CALLS_KEY = "tool_calls_this_turn"


def start_turn(callback_context: CallbackContext) -> None:
    """Each user message starts a new turn: no relayed answers and no tool calls yet."""
    callback_context.state[RELAY_KEY] = []
    callback_context.state[CALLS_KEY] = []


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
    tools=[search_current, search_historical, lookup_document, compare_studies, text_to_sql],
    # Thinking stays on (model default); temperature 0 so the same question routes the same way.
    generate_content_config=types.GenerateContentConfig(temperature=0),
    before_agent_callback=start_turn,
    before_tool_callback=limit_tool_calls,
    after_model_callback=relay_tool_answer,
    on_model_error_callback=busy_fallback,
)
