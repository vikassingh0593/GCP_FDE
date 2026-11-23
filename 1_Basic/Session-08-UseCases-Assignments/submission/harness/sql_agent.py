"""SQL analyst: the first specialist agent, called by the orchestrator as a tool (D67, D68).

Why an agent here, and only here (D68, rule 5): writing SQL needs a loop (write → check →
read the error or an empty result → fix → check again). The fixed pipeline (src/text2sql.ask)
tried once and could not reason about its result: it wrote event = 'Rash' and got 0 rows.

How it stays safe (the D68 rules):
  1. The orchestrator keeps the conversation: this agent is an ADK AgentTool, never a transfer.
  2. Safety is code inside its tools: try_sql and show_sql_result run every check of
     src/text2sql.py themselves (SELECT only, one statement, allowed views, BigQuery dry run of the
     real base tables, byte and row caps); the agent can only *try*, never skip a check.
  3. The user sees the rows word for word (D31): show_sql_result puts them in the relay; the
     agent's own words never reach the user. If it ends without a result, code says so.
  4. Its steps are capped in code (limit_sql_steps): MAX_SQL_TRIES tries and one result per question.
"""

from __future__ import annotations

import re
import time
import uuid

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.adk.models.google_llm import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

import rag_runtime as rt
import text2sql
from config import AGENT_MODEL, ASSISTANT_NAME, MAX_SQL_ROWS
from policy import CLINICAL_FIGURE
from tools import TRACE


SQL_RELAY_KEY = "relay_sql"        # verbatim results for the user; merged by the orchestrator's relay
SQL_STEPS_KEY = "sql_steps"        # tool calls this request, for the step cap
SQL_ATTEMPTS_KEY = "sql_attempts"  # every query tried and its error (logged with the result)
SQL_DONE_KEY = "sql_done"          # a result or "unanswerable" was shown
SQL_START_KEY = "sql_started"
MAX_SQL_TRIES = 4                  # try_sql calls per request; raise it if the evaluation shows valid repairs cut short
LIMITS = {"try_sql": MAX_SQL_TRIES, "show_sql_result": 2, "report_unanswerable": 1}  # only one result can succeed
PREVIEW_ROWS = 5


def _clean(sql: str) -> str:
    """The query as the agent wrote it, without markdown fences or a trailing semicolon."""
    sql = re.sub(r"^\s*```(?:sql)?\s*|\s*```\s*$", "", sql or "", flags=re.IGNORECASE)
    return sql.strip().rstrip(";").strip()


def _check(sql: str) -> tuple[bool, str, int]:
    """Every code check of the governed pipeline (D49): text rules, then the BigQuery dry run."""
    ok, error = text2sql.check_sql(sql)
    scanned = 0
    if ok:
        ok, error, scanned = text2sql.dry_run(sql)
    return ok, error, scanned


def _request(ctx) -> str:
    content = getattr(ctx, "user_content", None)
    return " ".join(p.text for p in (content.parts if content and content.parts else []) if p.text).strip()


def _result(outcome: str, answer: str, ctx, **extra) -> dict:
    """A result shaped like the runtime's, so it is logged and traced the same way."""
    started = ctx.state.get(SQL_START_KEY)
    result = {"log_id": uuid.uuid4().hex, "question": _request(ctx), "mode": "sql", "country": None,
              "filters": {"views": list(text2sql.SQL_VIEWS), "attempts": list(ctx.state.get(SQL_ATTEMPTS_KEY) or [])},
              "candidates": [], "reranked": [], "cards": [], "reasons": [], "sources": "", "notes": [],
              "latency_ms": {"total": round((time.time() - started) * 1000)} if started else {},
              "citation_check": "rows shown verbatim (no generation)", "outcome": outcome, "answer": answer}
    result.update(extra)
    return result


def _show(result: dict, ctx) -> None:
    """What the user will see (verbatim relay), the trace for scripts, and one agent_log row."""
    ctx.state[SQL_RELAY_KEY] = list(ctx.state.get(SQL_RELAY_KEY) or []) + [result["answer"]]
    ctx.state[SQL_DONE_KEY] = True
    TRACE.append({"call_id": None, "tool": "sql_analyst", "result": result})
    rt.log_question(result, "agent:sql_analyst")


# --- the agent's tools: it may try anything; the tools decide ----------------------

def try_sql(sql: str, tool_context: ToolContext) -> dict:
    """Check a SQL query and preview its result. Nothing is shown to the user.

    The checks are code: SELECT only, one statement, only the allowed views, then a BigQuery
    dry run (syntax, columns, the real tables read, bytes). If they pass, the query runs and
    you get its first rows, so you can judge the result.

    Args:
        sql: one BigQuery Standard SQL SELECT statement.

    Returns:
        ok: true if the query is valid and ran; error: the exact reason to fix;
        rows_total and preview: the result (0 rows often means a wrong text value).
    """
    sql = _clean(sql)
    ok, error, _ = _check(sql)
    total, preview = 0, []
    if ok:
        try:
            rows, total = text2sql.run_sql(sql)
            preview = [{k: text2sql._cell(v) for k, v in r.items()} for r in rows[:PREVIEW_ROWS]]
        except Exception as exc:  # a runtime error is something to fix, not a crash
            ok, error = False, f"BigQuery error: {str(exc)[:300]}"
    tool_context.state[SQL_ATTEMPTS_KEY] = list(tool_context.state.get(SQL_ATTEMPTS_KEY) or []) + [
        {"sql": sql, "ok": ok, "error": "" if ok else error, "rows": total}]
    if not ok:
        return {"ok": False, "error": error}
    return {"ok": True, "rows_total": total, "preview": preview,
            "hint": "0 rows: compare your text values with the listed Values before concluding there is no data"
                    if total == 0 else ""}


def show_sql_result(tool_context: ToolContext) -> dict:
    """Show the result of your LAST SUCCESSFUL try_sql to the user, word for word, with its SQL.
    Call it once, when that preview answers the question. You do not retype the query.

    Returns:
        ok and rows_total. The user sees the rows and the SQL, never your words.
    """
    # Takes the query from the last successful try, never from the model: retyping a long query
    # introduced a typo in testing ("min_rate_for_for_event"), and the valid result was lost.
    attempts = tool_context.state.get(SQL_ATTEMPTS_KEY) or []
    last_ok = next((a for a in reversed(attempts) if a.get("ok")), None)
    if last_ok is None:
        return {"ok": False, "error": "no successful try_sql yet: call try_sql first"}
    sql = last_ok["sql"]
    ok, error, scanned = _check(sql)  # checked again all the same: code never trusts the state blindly
    if not ok:
        return {"ok": False, "error": f"not shown: {error}"}
    rows, total = text2sql.run_sql(sql)
    _show(_result("answered", text2sql.format_rows(rows, total, sql), tool_context, sql=sql,
                  rows_total=total, bytes_scanned=scanned), tool_context)
    return {"ok": True, "rows_total": total}


def report_unanswerable(reason: str, tool_context: ToolContext) -> dict:
    """Tell the user the structured data cannot answer this question (for example, no such
    column). Call it instead of show_sql_result. Never invent data.

    Args:
        reason: a short reason, e.g. "the views have no patient ages".
    """
    shown = (reason or "").strip().rstrip(".")
    if not shown or CLINICAL_FIGURE.search(shown):
        shown = "the views have no matching data"
    answer = (f"This can't be answered from the structured data ({shown}). Ask me with a "
              "country or a document ID and I'll search the documents instead.")
    _show(_result("insufficient", answer, tool_context, reasons=[reason]), tool_context)
    return {"ok": True}


# --- callbacks: limits and the never-silent ending, all in code ---------------------

def start_sql(callback_context: CallbackContext) -> None:
    """Each request starts with no steps, no attempts and nothing shown."""
    callback_context.state[SQL_STEPS_KEY] = {}
    callback_context.state[SQL_ATTEMPTS_KEY] = []
    callback_context.state[SQL_DONE_KEY] = False
    callback_context.state[SQL_START_KEY] = time.time()


def limit_sql_steps(tool, args: dict, tool_context) -> dict | None:
    """D67: the loop is capped in code: MAX_SQL_TRIES tries and one result per request.
    Returning a dict skips the tool and hands the dict to the agent as its result."""
    if tool_context.state.get(SQL_DONE_KEY):
        return {"ok": False, "error": "a result was already shown: stop and reply in one sentence"}
    steps = dict(tool_context.state.get(SQL_STEPS_KEY) or {})
    limit = LIMITS.get(tool.name, 1)
    if steps.get(tool.name, 0) >= limit:
        return {"ok": False, "error": f"limit of {limit} {tool.name} calls reached: report what you have"}
    steps[tool.name] = steps.get(tool.name, 0) + 1
    tool_context.state[SQL_STEPS_KEY] = steps
    return None


def finish_sql(callback_context: CallbackContext) -> None:
    """If the agent ended without showing anything, code tells the user why: never silence,
    never the agent's own words."""
    if callback_context.state.get(SQL_DONE_KEY):
        return None
    attempts = callback_context.state.get(SQL_ATTEMPTS_KEY) or []
    if attempts and not attempts[-1].get("ok"):
        why = attempts[-1]["error"]
    else:
        why = "stopped before showing a result" if attempts else "no query was tried"
    answer = (f"I couldn't build a safe query for this question ({why[:200]}). Try asking it more simply, "
              "or ask with a country to search the documents.")
    _show(_result("blocked", answer, callback_context, reasons=[a["error"] for a in attempts if a.get("error")]),
          callback_context)
    return None


def busy(callback_context: CallbackContext, llm_request, error: Exception) -> LlmResponse | None:
    """Gemini still busy after its retries: end the loop; finish_sql then tells the user."""
    if any(s in str(error) for s in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE")):
        callback_context.state[SQL_ATTEMPTS_KEY] = list(callback_context.state.get(SQL_ATTEMPTS_KEY) or []) + [
            {"sql": "", "ok": False, "error": "the SQL service is busy (Google Cloud rate limit), try again in a minute"}]
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text="busy")]))
    return None


INSTRUCTION = """You are the SQL analyst of {assistant}. You answer ONE analytical question (a count, ranking,
total or list) from two read-only BigQuery views, by writing SQL. You never answer from your own knowledge.

Views (the only data you may read):
{schema}

SQL rules:
{rules}

How to work:
1. Write one query and call try_sql. It checks the query in code (SELECT only, allowed views, BigQuery dry
   run) and, if it is valid, runs it and shows you the first rows. Nothing is shown to the user yet.
2. If try_sql returns an error, read it, fix the query and call try_sql again. If it returns 0 rows, compare
   your text values with the listed Values (spelling, case) before concluding the data has none.
   At most {tries} tries.
3. When the preview answers the question, call show_sql_result (no arguments): it shows the user the
   result of your last successful try_sql, rows and SQL, word for word.
4. If no query over these views can answer the question (the data is not there), call report_unanswerable
   with a short reason. Never invent data, never change data.
5. Then reply with one short sentence. The user never sees your words, only the tool's result.
"""

SQL_LLM = Gemini(model=AGENT_MODEL, retry_options=types.HttpRetryOptions(
    attempts=5, initial_delay=2.0, max_delay=16.0, exp_base=2.0, http_status_codes=[429, 503]))

sql_analyst = Agent(
    name="sql_analyst",
    model=SQL_LLM,
    description=("Answers COUNT, RANKING, TOTAL or LIST questions from the structured data (the document register "
                 "and the adverse-event rates per study) by writing, checking and running a read-only SQL query. "
                 "Pass the user's question as the request."),
    # Built from BigQuery metadata and real column values when the agent starts (no hand-written schema).
    instruction=(INSTRUCTION.replace("{assistant}", ASSISTANT_NAME).replace("{schema}", text2sql.schema_text())
                 .replace("{rules}", text2sql.SQL_STYLE_RULES.replace("{max_rows}", str(MAX_SQL_ROWS)))
                 .replace("{tries}", str(MAX_SQL_TRIES))),
    tools=[try_sql, show_sql_result, report_unanswerable],
    generate_content_config=types.GenerateContentConfig(temperature=0),
    before_agent_callback=start_sql,
    before_tool_callback=limit_sql_steps,
    after_agent_callback=finish_sql,
    on_model_error_callback=busy,
)

# The orchestrator calls it like any tool (D68 rule 1): it keeps the conversation and the relay.
sql_analyst_tool = AgentTool(agent=sql_analyst)
