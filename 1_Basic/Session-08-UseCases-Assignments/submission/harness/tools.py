"""Agent tools: thin wrappers over the search runtime (src/rag_runtime.py).

The agent decides WHICH tool and fills in what the user asked (the question,
the country, a date, a document ID). Everything that must be the same every
time lives in the runtime or here, in code: the status rule for the mode, the
hard filters, the checks, the date validation and the fixed notes.

Each tool appends its checked answer to a list under RELAY_KEY in the session
state. The agent's after_model_callback then shows exactly those texts to the
user, so the model cannot add to or reword an answer after the checks ran
(decision D31). A list, not one slot (D51): a question with several parts may
call several tools in one turn, and every checked part must reach the user;
with one slot the second answer silently overwrote the first.
The only additions are fixed lines built here by code (D31 table, §8):
  - jurisdiction note when the country differs from the previous question (D40)
  - the date a historical answer used, so the user sees how "in 2021" was read (D38)
  - "earlier version exists" after a current label answer (D43, from the runtime)

Pattern from session-06 `harness/tools.py` and session-09 `text2sql.py`.
"""

from __future__ import annotations

import re
import sys
import traceback
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from google.adk.tools import ToolContext  # noqa: E402

import rag_runtime as rt  # noqa: E402
import text2sql  # noqa: E402
import escalation  # noqa: E402


RELAY_KEY = "relay_answer"

# Trace capture for scripts (D61): every tool call's FULL runtime result, keyed by the ADK
# function-call ID. The demo and evaluation scripts read it to print the brief's trace
# (filters → candidates → reranked → evidence → answer); the agent never sees it.
TRACE: list[dict] = []
# D40 compares with the turn DIRECTLY before, not with any earlier search in the session
# (bug found in Step 8: after a Germany search, a catalogue question, then a US question,
# the note wrongly said "your previous question was about Germany").
TURN_COUNTRY_KEY = "country_this_turn"
PREVIOUS_COUNTRY_KEY = "country_previous_turn"


def start_turn_state(state) -> None:
    """Called by the agent at the start of every user turn: this turn's country becomes the previous one."""
    state[PREVIOUS_COUNTRY_KEY] = state.get(TURN_COUNTRY_KEY)
    state[TURN_COUNTRY_KEY] = None
ESCALATED_KEY = "escalated_this_turn"  # read by the agent's patient fallback (D53)


def _evidence_summary(result: dict) -> list[dict]:
    """A short view of the evidence for the agent (and the adk web trace)."""
    # .get: STRUCTURED DATA and COMPUTED cards (Step 6) have no page or table
    return [{"id": c["id"], "document": c["chunk"].get("document_id"), "page": c["chunk"].get("page_start"),
             "table": c["chunk"].get("table_id"), "role": c["role"]} for c in result.get("cards", [])]


def _jurisdiction_note(result: dict, tool_context: ToolContext) -> str:
    """D40: a fixed note when this answer's country differs from the previous question's."""
    country, previous = result.get("country"), tool_context.state.get(PREVIOUS_COUNTRY_KEY)
    if country:
        tool_context.state[TURN_COUNTRY_KEY] = country
    if country and previous and country != previous:
        return f"Note: this answer is for {country}. Your previous question was about {previous}."
    return ""


def _relay(result: dict, tool_context: ToolContext, header: list[str] | None = None) -> dict:
    """Store the exact text the user must see, and return a compact result to the agent."""
    # Fixed lines built by code go first (D40 jurisdiction, D38 date used, D64 premise), then the checked answer.
    parts = [line for line in (header or []) + result.get("lead_notes", []) if line] + [result["answer"]]
    if result.get("sources"):
        parts.append(result["sources"])
    parts += result.get("notes", [])
    # Assign a new list (not .append) so ADK records the state change.
    tool_context.state[RELAY_KEY] = list(tool_context.state.get(RELAY_KEY) or []) + ["\n\n".join(parts)]
    TRACE.append({"call_id": getattr(tool_context, "function_call_id", None), "result": result})
    return {
        "outcome": result["outcome"],
        "answer": result["answer"],
        "sources": result.get("sources", ""),
        "filters_applied": result.get("filters", {}),
        "evidence": _evidence_summary(result),
        "reasons": result.get("reasons", []),
    }


def _failed(exc: Exception, question: str = "", caller: str = "agent") -> dict:
    """Never crash the conversation, and never fail silently.

    The user gets a polite message; the full traceback goes to the adk web terminal and an
    `error` row goes to agent_log, so the health report counts it. (Found in testing: a first
    search failed, the retry worked, and agent_log had no trace of the failure.)
    """
    traceback.print_exc()
    result = {"log_id": uuid.uuid4().hex, "question": question or "", "mode": None, "country": None,
              "filters": {}, "cards": [], "candidates": [], "latency_ms": {}, "sources": "",
              "outcome": "error", "answer": "The search service failed; please try again in a minute.",
              "reasons": [f"{type(exc).__name__}: {str(exc)[:300]}"],
              "citation_check": f"not run: {type(exc).__name__}: {str(exc)[:150]}"}
    try:
        rt.log_question(result, caller)
    except Exception:
        pass  # logging must never break the reply
    return result


def _clarify(text: str) -> dict:
    return {"outcome": "clarify", "answer": text, "sources": "", "cards": [], "filters": {}, "reasons": []}


def search_current(question: str, country: str, product: str, tool_context: ToolContext) -> dict:
    """Answer a question about the CURRENT, approved product guidance for one country.

    Use it for what applies now: current dose, current monitoring, what the current
    label or a current safety bulletin says, when the country is known.

    Do NOT use it for: earlier, previous or superseded guidance (use search_historical);
    a specific document ID (use lookup_document); comparing studies; analytics; or
    advice about an individual patient.

    Args:
        question: The user's question, in their own words.
        country: The country the question is about, as the user named it.
        product: The product the user named, or "" (only needed when the CATALOGUE lists several).

    Returns:
        outcome: answered, partial, insufficient, not_found, clarify, blocked or error.
        answer: the checked answer with [E#] citations (shown to the user verbatim).
        sources: the cited documents with page and link.
        filters_applied, evidence, reasons: how the answer was produced.
    """
    try:
        result = rt.answer(question, mode="current", country=country, product=product or None,
                           caller="agent:search_current")
    except Exception as exc:
        result = _failed(exc, question, "agent:search_current")
    return _relay(result, tool_context, [_jurisdiction_note(result, tool_context)])


def search_historical(question: str, country: str, as_of: str, product: str, tool_context: ToolContext) -> dict:
    """Answer a question about EARLIER guidance for one country: what applied on a past date,
    what an earlier or superseded version said, or what changed between versions.

    Superseded documents are allowed and every one is labelled HISTORICAL in the answer.

    Args:
        question: The user's question, in their own words.
        country: The country the question is about, as the user named it.
        as_of: The past date the user means, as YYYY-MM-DD. A month means its last day,
            a year means 31 December of that year. Use "" when the user asks what changed
            or what an earlier version said, without a time point.
        product: The product the user named, or "" (only needed when the CATALOGUE lists several).

    Returns:
        outcome: answered, partial, insufficient, not_found, clarify, blocked or error.
        answer: the checked answer (shown to the user verbatim).
        sources, filters_applied, evidence, reasons: as for search_current.
    """
    as_of = (as_of or "").strip()
    header = ""
    if as_of:
        # D38: the agent turns the user's words into a date; code checks it.
        try:
            day = date.fromisoformat(as_of) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of) else None
        except ValueError:
            day = None
        if day is None:
            return _relay(_clarify(f"I could not read \"{as_of}\" as a date. Which day, month or year do you mean?"),
                          tool_context)
        if day > date.today():
            return _relay(_clarify(f"{as_of} is in the future. For what applies now, ask for the current guidance."),
                          tool_context)
        header = f"Historical view: documents in effect on {as_of}."
    else:
        header = "Historical view: all versions up to today; earlier ones are marked HISTORICAL."
    try:
        result = rt.answer(question, mode="historical", country=country, as_of=as_of or None,
                           product=product or None, caller="agent:search_historical")
    except Exception as exc:
        result = _failed(exc, question, "agent:search_historical")
    if result["outcome"] in ("not_found", "error"):
        header = ""  # the message already says what was searched
    return _relay(result, tool_context, [_jurisdiction_note(result, tool_context), header])


def lookup_document(document_id: str, table: str, rows: str, question: str, tool_context: ToolContext) -> dict:
    """Look up ONE document by its exact ID (the IDs are listed in the CATALOGUE).

    Three uses, depending on what the user asked:
      - a table from it: set `table` to the user's words ("Table 2", "the dosing table");
        the stored table is shown word for word (long tables: first rows, total, a filter offer);
        set `rows` to the row labels the user names, comma-separated;
      - a question about its content: set `question`;
      - only the ID ("what is <ID>?"): leave table, rows and question empty to get its facts.

    The document's own status decides whether it is shown as current or HISTORICAL.

    Args:
        document_id: The document ID exactly as the user wrote it.
        table: The table the user asked for, in their words, or "".
        rows: Rows the user asked for, comma-separated, or "".
        question: The user's question about this document, or "".

    Returns:
        outcome: answered, not_found, clarify (several tables match: the user picks one), or error.
        answer: shown to the user verbatim.
    """
    try:
        result = rt.lookup(document_id, table=table or "", rows=rows or "", question=question or "",
                           caller="agent:lookup_document")
    except Exception as exc:
        result = _failed(exc, question or table or document_id, "agent:lookup_document")
    return _relay(result, tool_context)


def compare_studies(study_ids: list[str], event: str, question: str, tool_context: ToolContext) -> dict:
    """Compare adverse-event evidence ACROSS STUDIES (e.g. "Compare AE evidence in HN-204 and HN-311").

    Numbers come from a verified query on the registry database, each study's own table is
    cited, and differences are computed by code. Also use it for a question that mixes study
    numbers with what the studies say about them.

    Args:
        study_ids: The study IDs the user named, at least two, e.g. ["HN-204", "HN-311"].
        event: One adverse event if the user named one (e.g. "nausea"), else "".
        question: The user's question, in their own words.

    Returns:
        outcome: answered, partial, not_found, clarify (not a study, or fewer than two), blocked or error.
        answer: the checked comparison (shown to the user verbatim).
    """
    try:
        result = rt.compare(study_ids, event=event or "", question=question or "", caller="agent:compare_studies")
    except Exception as exc:
        result = _failed(exc, question, "agent:compare_studies")
    return _relay(result, tool_context)


def text_to_sql(question: str, tool_context: ToolContext) -> dict:
    """Answer a COUNT, RANKING, TOTAL or LIST question from the structured data with a read-only query.

    For example: "Which study had the highest rash rate?", "How many approved documents per
    country?", "List the superseded documents". The SQL is written inside the tool and checked by
    code before it runs; the rows and the SQL are shown word for word.

    Do NOT use it for what a document says (use the search tools) or to change any data.

    Args:
        question: The user's question, in their own words.

    Returns:
        outcome: answered, insufficient (the data cannot answer it), blocked (no safe query), or error.
        answer: the rows and the SQL (shown to the user verbatim).
    """
    try:
        result = text2sql.ask(question, caller="agent:text_to_sql")
    except Exception as exc:
        result = _failed(exc, question, "agent:text_to_sql")
    return _relay(result, tool_context)


def escalate(reason: str, question: str, general_question: str, country: str, tool_context: ToolContext) -> dict:
    """Hand the question to a person at Medical Information (human in the loop).

    Use it for: a question about ONE specific patient (a treatment decision), or when the user
    asks to route a question ("route it", "yes, escalate") after the assistant could not answer.

    Args:
        reason: "patient_specific" or "user_request".
        question: The user's question as asked (for a "route it" request: the earlier question).
        general_question: For a patient case: the same question WITHOUT any patient details (no
            age, no personal lab values, no "my patient"), as a general information question,
            e.g. "renal dosing guidance for moderate impairment and hepatic monitoring". Else "".
        country: The country if known, else "".

    Returns:
        outcome: escalated (with an escalation ID) or error (the hand-off could not be recorded).
        answer: the fixed hand-off text, plus a general reference for a patient case (shown verbatim).
    """
    try:
        result = escalation.escalate(reason, question, general_question or "", country or None,
                                     caller="agent:escalate")
    except Exception as exc:
        result = _failed(exc, question, "agent:escalate")
    tool_context.state[ESCALATED_KEY] = True  # the hand-off path was taken (its message says if recording failed)
    return _relay(result, tool_context)
