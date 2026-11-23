"""The orchestrator end to end inside a real ADK Runner, with a scripted model and no cloud.

Covers what the brief's minimum acceptance asks the runtime to prove:
correlation ID on every run, fail closed without context, specialist down ->
partial answer with no stock numbers, budgets that block, citations checked,
and the escalation write waiting for the analyst's confirmation.
"""

from __future__ import annotations

import asyncio

from google.adk.agents.run_config import RunConfig
from google.adk.sessions import InMemorySessionService
from google.genai import types

from common import config
from fakes import ORDER_ROWS, ScriptedModel, call, fake_query_rows, last_responses, say

DEAD_CARD = "http://127.0.0.1:9/.well-known/agent-card.json"   # nothing listens on port 9


def make_runtime(monkeypatch, steps, rows=None):
    from orchestrator import runtime as runtime_module
    from orchestrator.tools import orders

    monkeypatch.setattr(orders, "query_rows", fake_query_rows({"orders": list((rows or ORDER_ROWS).values())}))
    rt = runtime_module.Runtime(card_url=DEAD_CARD, timeout=3, session_service=InMemorySessionService())
    rt.app.root_agent.model = ScriptedModel(steps=steps)
    return rt


def run(coro):
    return asyncio.run(coro)


async def _session(rt, user="analyst_test"):
    return await rt.create_session(user)


def test_specialist_down_gives_partial_answer_without_stock(monkeypatch):
    def final(request):
        r = last_responses(request)
        order_ev = r["get_order"]["evidence_id"]
        assert r["check_fulfilment"]["status"] == "error"          # the dead specialist became an error result
        return (f"OUTCOME: partial\nCAUSE: none\nFULFILABLE: unknown\n"
                f"ANSWER: Fulfilment check unavailable.\nOBSERVATIONS:\n- 40 ordered at WH-BLR-01 [{order_ev}]")

    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"),
                                    call("check_fulfilment", order_id="ORD-78421"), say(final)])

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421."), s

    result, session = run(go())
    assert result.header == {"outcome": "partial", "cause": "none", "fulfilable": "unknown"}
    assert result.correlation_id.startswith("corr-")
    trace = result.trace
    assert trace["correlation_id"] == result.correlation_id and trace["termination"] == "NORMAL"
    assert [t["tool"] for t in trace["tools"]] == ["get_order", "check_fulfilment"]
    assert trace["tools"][1]["outcome"] == "error"
    assert any(d.get("a2a") == "fulfilment_specialist" for d in trace["details"])
    assert trace["invalid_citations"] == [] and len(trace["cited_ids"]) == 1
    assert trace["tokens"] == {"in": 300, "out": 30}            # 3 model calls x the fake's usage


def test_session_state_holds_the_current_order(monkeypatch):
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"), say("OUTCOME: answer\nCAUSE: none")])

    async def go():
        s = await _session(rt)
        await rt.run_turn("analyst_test", s.id, "Look up ORD-78421")
        return await rt.get_session("analyst_test", s.id)

    session = run(go())
    assert session.state["current_order_id"] == "ORD-78421"


def test_invented_evidence_id_is_flagged(monkeypatch):
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"),
                                    say("OUTCOME: cause_named\nOBSERVATIONS:\n- 7 available [EV-INV-WH-BLR-01/SKU-74512-abcdef]")])

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")

    result = run(go())
    assert result.trace["invalid_citations"] == ["EV-INV-WH-BLR-01/SKU-74512-abcdef"]
    assert any("Unverified evidence IDs" in w for w in result.warnings)


def test_follow_up_turn_may_cite_evidence_from_an_earlier_turn(monkeypatch):
    def cite_first_turn(request):
        return "OUTCOME: answer\nCAUSE: none\nANSWER: as before [EV-ORD-ORD-78421-" + _order_suffix() + "]"

    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"), say("OUTCOME: check_next"),
                                    say(cite_first_turn)])

    async def go():
        s = await _session(rt)
        await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")
        return await rt.run_turn("analyst_test", s.id, "And what was its status again?")

    second = run(go())
    assert second.trace["tool_calls"] == 0                   # nothing looked up in this turn
    assert second.trace["invalid_citations"] == []            # but the ID came from the earlier turn


def _order_suffix() -> str:
    from common import results
    from fakes import ORDER_ROWS
    return results.evidence_id("ORD", "ORD-78421", ORDER_ROWS["ORD-78421"]["extracted_at"]).rsplit("-", 1)[1]


def test_repeated_identical_calls_are_blocked(monkeypatch):
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421")])   # the model loops forever

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")

    result = run(go())
    assert result.trace["termination"] in ("REPEATED_CALL_PATTERN", "MODEL_BUDGET_EXCEEDED")
    blocked = [t for t in result.trace["tools"] if str(t["outcome"]).startswith("blocked")]
    assert blocked, result.trace["tools"]
    assert result.trace["model_calls"] <= config.MAX_MODEL_CALLS_PER_INVOCATION


def _small_budget(rt, model_calls):
    from common.harness.policy import ExecutionPolicy
    rt.harness.policy = ExecutionPolicy(max_model_calls=model_calls, max_tool_calls=10, max_same_tool_calls=3,
                                        max_failures=2, max_elapsed_seconds=60)


def test_last_model_call_is_kept_for_the_answer(monkeypatch):
    rt = make_runtime(monkeypatch, [
        call("get_order", order_id="ORD-78421"),
        call("get_order", order_id="ORD-78421"),          # call 2 of 3: tools stop here
        say("OUTCOME: partial\nCAUSE: none\nFULFILABLE: unknown\nANSWER: Stopped early; order found."),
    ])
    _small_budget(rt, 3)

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")

    result = run(go())
    assert result.header["outcome"] == "partial"                # a real answer, not the stop message
    t = result.trace
    assert t["termination"] == "MODEL_BUDGET_EXCEEDED" and t["closing_call_used"] and not t["hard_stop"]
    assert t["model_calls"] == 3 and [x["outcome"] for x in t["tools"]] == ["ok", "blocked:MODEL_BUDGET_EXCEEDED"]
    assert t["failures"] == 0                                   # a harness block is not a tool failure


def test_closing_call_that_asks_for_tools_ends_in_a_hard_stop(monkeypatch):
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421")])   # never answers
    _small_budget(rt, 3)

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")

    result = run(go())
    assert result.answer.startswith("HARNESS_STOP") and result.trace["hard_stop"]
    assert result.trace["model_calls"] == 3


def test_tool_budget_stop_still_gets_an_answer(monkeypatch):
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421")] * 4 +
                      [say("OUTCOME: partial\nCAUSE: none\nANSWER: The same lookup kept repeating.")])

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")

    result = run(go())
    assert result.trace["termination"] == "REPEATED_CALL_PATTERN"
    assert result.header["outcome"] == "partial" and result.trace["closing_call_used"]


def test_run_without_context_is_refused(monkeypatch):
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421")])

    async def go():
        s = await _session(rt)
        texts = []
        async for event in rt.runner.run_async(user_id="analyst_test", session_id=s.id,
                                               new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
                                               run_config=RunConfig()):
            if event.content and event.content.parts:
                texts += [p.text for p in event.content.parts if p.text]
        return texts

    texts = run(go())
    assert texts and texts[0].startswith("HARNESS_STOP")
    assert rt.app.root_agent.model.calls == 0          # no model call, no tool call


def test_escalation_waits_for_confirmation_and_decline_writes_nothing(monkeypatch):
    from orchestrator.tools import escalation

    writes = []
    monkeypatch.setattr(escalation, "_ensure_table", lambda: writes.append("table"))
    rt = make_runtime(monkeypatch, [
        call("escalate_case", order_id="ORD-78421", owner_team="Logistics Operations",
             summary="Order and carrier disagree.", check_next=["handover scan"], evidence_ids=[]),
        say("OUTCOME: escalate\nCAUSE: none\nFULFILABLE: not_applicable\nANSWER: Escalation not saved."),
    ])

    async def go():
        s = await _session(rt)
        first = await rt.run_turn("analyst_test", s.id, "ORD-78421 says shipped. Is it on its way?")
        second = await rt.confirm("analyst_test", s.id, first.pending_confirmation["request_id"], False)
        return first, second

    first, second = run(go())
    assert first.pending_confirmation["tool"] == "escalate_case"
    assert first.pending_confirmation["args"]["owner_team"] == "Logistics Operations"
    assert writes == []                                  # declined: the tool never ran
    assert second.header["outcome"] == "escalate"
    # The resumed run is a new request, linked to the one that asked for the confirmation.
    assert second.correlation_id != first.correlation_id
    assert second.trace["parent_correlation_id"] == first.correlation_id


def test_tool_outside_the_allowlist_never_runs(monkeypatch):
    from common.harness import HarnessPlugin
    from common.harness.trace import InvocationTrace
    from common.harness.context import RequestContext
    from common.harness.policy import ExecutionPolicy
    from types import SimpleNamespace

    plugin = HarnessPlugin("orchestrator", allowed_tools={"get_order"})
    plugin.active["inv-1"] = InvocationTrace("orchestrator", "inv-1", RequestContext.create("u1"),
                                             ExecutionPolicy.from_config())
    out = run(plugin.before_tool_callback(tool=SimpleNamespace(name="drop_table"), tool_args={},
                                          tool_context=SimpleNamespace(invocation_id="inv-1", function_call_id="f1")))
    assert out["status"] == "error" and out["error_type"] == "policy"
