"""Offline tests for the SQL analyst agent's guardrails (D67): its tools and callbacks, no cloud.

The agent's own Gemini calls are not replayed; what matters for safety is in code and tested
here: every check runs inside the tools, the loop is capped, results reach the user verbatim,
and the agent never ends in silence.

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

from google.genai import types  # noqa: E402

import sql_agent as sa  # noqa: E402
import text2sql  # noqa: E402

VIEW = text2sql.view_ids()["v_adverse_events"]
GOOD = f"SELECT study_id, treatment_rate_pct FROM `{VIEW}` WHERE event = 'rash' ORDER BY treatment_rate_pct DESC LIMIT 1"
ZERO = f"SELECT study_id, treatment_rate_pct FROM `{VIEW}` WHERE event = 'Rash' ORDER BY treatment_rate_pct DESC LIMIT 1"


def _ctx(question="Which study had the highest rash rate?"):
    ctx = SimpleNamespace(state={}, user_content=types.Content(role="user", parts=[types.Part(text=question)]))
    sa.start_sql(ctx)
    return ctx


def test_try_sql_reports_errors_and_previews_rows_without_showing_anything():
    ctx = _ctx()
    bad = sa.try_sql(f"DROP TABLE `{VIEW}`", ctx)
    assert bad["ok"] is False and "SELECT" in bad["error"]
    good = sa.try_sql(f"```sql\n{GOOD};\n```", ctx)  # fences and semicolon are cleaned
    assert good["ok"] and good["rows_total"] == 1 and good["preview"][0]["study_id"] == "HN-402"
    assert not ctx.state.get(sa.SQL_RELAY_KEY)  # nothing reaches the user from a try
    assert [a["ok"] for a in ctx.state[sa.SQL_ATTEMPTS_KEY]] == [False, True]


def test_zero_rows_come_back_with_a_hint_to_check_the_values():
    out = sa.try_sql(ZERO, _ctx())
    assert out["ok"] and out["rows_total"] == 0 and "Values" in out["hint"]


def test_show_sql_result_uses_the_last_successful_try_and_checks_it_again():
    ctx = _ctx()
    assert sa.show_sql_result(ctx)["ok"] is False  # nothing tried yet: nothing to show
    ctx.state[sa.SQL_ATTEMPTS_KEY] = [{"sql": "SELECT chunk_id FROM `tredence-fde-1.medevidence_v1_vks.chunks` LIMIT 1",
                                       "ok": True, "error": "", "rows": 1}]  # a tampered "success"
    assert sa.show_sql_result(ctx)["ok"] is False and not ctx.state.get(sa.SQL_RELAY_KEY)  # checked again, refused
    sa.try_sql(GOOD, ctx)
    sa.try_sql(f"DROP TABLE `{VIEW}`", ctx)  # a later failed try does not replace the last success
    shown = sa.show_sql_result(ctx)
    assert shown["ok"] and "| HN-402 | 19.7 |" in ctx.state[sa.SQL_RELAY_KEY][-1]
    assert "SQL:" in ctx.state[sa.SQL_RELAY_KEY][-1] and ctx.state[sa.SQL_DONE_KEY]


def test_the_loop_is_capped_in_code():
    ctx = _ctx()
    try_tool, show_tool = SimpleNamespace(name="try_sql"), SimpleNamespace(name="show_sql_result")
    for _ in range(sa.MAX_SQL_TRIES):
        assert sa.limit_sql_steps(try_tool, {"sql": "x"}, ctx) is None
    assert sa.limit_sql_steps(try_tool, {"sql": "x"}, ctx)["ok"] is False  # one try too many
    assert sa.limit_sql_steps(show_tool, {}, ctx) is None
    ctx.state[sa.SQL_DONE_KEY] = True
    assert sa.limit_sql_steps(show_tool, {}, ctx)["ok"] is False  # nothing after a result


def test_ending_without_a_result_is_never_silent():
    ctx = _ctx()
    sa.try_sql(f"DROP TABLE `{VIEW}`", ctx)
    sa.finish_sql(ctx)
    assert "couldn't build a safe query" in ctx.state[sa.SQL_RELAY_KEY][-1]
    ctx2 = _ctx()
    sa.try_sql(GOOD, ctx2)
    sa.finish_sql(ctx2)  # a valid query existed but was never shown: say so, never "no valid query"
    assert "stopped before showing a result" in ctx2.state[sa.SQL_RELAY_KEY][-1]
    assert "SELECT" in ctx.state[sa.SQL_RELAY_KEY][-1]  # the last real error is named


def test_unanswerable_is_said_plainly_and_without_figures():
    ctx = _ctx("What is the average age of patients in HN-204?")
    sa.report_unanswerable("The views have no patient ages.", ctx)
    assert ctx.state[sa.SQL_RELAY_KEY][-1].startswith("This can't be answered from the structured data (The views")
    ctx2 = _ctx()
    sa.report_unanswerable("only 25 mg rows exist", ctx2)  # a clinical figure in the agent's words is not shown
    assert "25 mg" not in ctx2.state[sa.SQL_RELAY_KEY][-1]
