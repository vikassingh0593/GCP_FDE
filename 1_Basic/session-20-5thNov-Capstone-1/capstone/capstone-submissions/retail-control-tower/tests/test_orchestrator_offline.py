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


def make_runtime(monkeypatch, steps, rows=None, session_service=None):
    from orchestrator import runtime as runtime_module
    from orchestrator.tools import orders

    monkeypatch.setattr(orders, "query_rows", fake_query_rows({"orders": list((rows or ORDER_ROWS).values())}))
    rt = runtime_module.Runtime(card_url=DEAD_CARD, timeout=3,
                                session_service=session_service or InMemorySessionService())
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
    assert trace["build"]["model"] == config.ORCHESTRATOR_MODEL and len(trace["build"]["instruction_sha"]) == 12


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
    assert "HARNESS_STOP" in result.answer and result.trace["hard_stop"]
    assert result.header["outcome"] == "partial"                 # the guard gives the stop message a header
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

    writes, seen_by_model = [], []
    monkeypatch.setattr(escalation, "_ensure_table", lambda: writes.append("table"))
    answer = say("OUTCOME: escalate\nCAUSE: none\nFULFILABLE: not_applicable\nANSWER: Escalation declined.")

    def answer_after_decline(llm_request):
        # What the model is told about the declined call (the last function response it sees).
        for content in llm_request.contents:
            for part in content.parts or []:
                if part.function_response and part.function_response.name == "escalate_case":
                    seen_by_model.append(dict(part.function_response.response or {}))
        return answer(llm_request)

    rt = make_runtime(monkeypatch, [
        call("escalate_case", order_id="ORD-78421", owner_team="Logistics Operations",
             summary="Order and carrier disagree.", check_next=["handover scan"], evidence_ids=[]),
        answer_after_decline,
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
    # The model is told the analyst declined, not ADK's bare "rejected" error it read as a failure on GCP.
    assert seen_by_model and seen_by_model[-1]["status"] == "declined" and seen_by_model[-1]["saved"] is False
    assert second.header["outcome"] == "escalate"
    # The resumed run is a new request, linked to the one that asked for the confirmation.
    assert second.correlation_id != first.correlation_id
    assert second.trace["parent_correlation_id"] == first.correlation_id


def test_the_corrected_answer_is_what_the_session_keeps(monkeypatch):
    """Found in a live check: the guard fixed the answer the analyst saw, but the session kept the model's
    original text, so a reopened session and the next turn's history showed the unchecked header."""
    history = []
    unproven = say("OUTCOME: cause_named\nCAUSE: inventory_shortage\nFULFILABLE: no\nANSWER: Short of stock.")

    def next_turn(llm_request):
        history.extend(p.text for c in llm_request.contents for p in (c.parts or []) if p.text)
        return say("OUTCOME: answer\nCAUSE: none\nFULFILABLE: unknown\nANSWER: See above.")(llm_request)

    # No fulfilment check ran, so neither the cause nor the stock verdict is proven.
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"), unproven, next_turn])

    async def go():
        s = await _session(rt)
        first = await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")
        second = await rt.run_turn("analyst_test", s.id, "And what was the cause?")
        return first, second, await rt.get_session("analyst_test", s.id)

    first, second, session = run(go())
    assert first.header == {"outcome": "check_next", "cause": "none", "fulfilable": "unknown"}
    assert "CHECKED BY CODE:" in first.answer and any("Checked by code" in w for w in first.warnings)
    replay = [t["text"] for t in rt.transcript(session) if t["role"] == "agent"]
    assert "FULFILABLE: unknown" in replay[0] and "CHECKED BY CODE:" in replay[0]
    assert "FULFILABLE: no" not in replay[0]
    seen_by_model = "\n".join(history)
    assert "CAUSE: none" in seen_by_model and "CAUSE: inventory_shortage" not in seen_by_model


def test_a_message_naming_an_order_starts_with_a_fresh_lookup(monkeypatch):
    """Found in a live check: asking "Investigate ORD-78421" again was answered from memory, no tools."""
    modes = []

    def record(step):
        def wrapped(llm_request):
            tc = llm_request.config.tool_config
            fc = tc.function_calling_config if tc else None
            modes.append((str(fc.mode) if fc else None, list(fc.allowed_function_names or []) if fc else []))
            return step(llm_request)
        return wrapped

    answer = say("OUTCOME: answer\nCAUSE: none\nFULFILABLE: unknown\nANSWER: ok")
    rt = make_runtime(monkeypatch, [
        record(call("get_order", order_id="ORD-78421")), record(answer),     # turn 1
        record(call("get_order", order_id="ORD-78421")), record(answer),     # turn 2: same order again
        record(answer),                                                       # turn 3: no order ID
    ])

    async def go():
        s = await _session(rt)
        for text in ("Investigate ORD-78421.", "Investigate ORD-78421", "And what was the cause?"):
            await rt.run_turn("analyst_test", s.id, text)

    run(go())
    forced = [m for m in modes if m[0] and "ANY" in m[0]]
    assert len(modes) == 5
    assert modes[0][1] == ["get_order"] and modes[2][1] == ["get_order"]   # each turn naming an order
    assert len(forced) == 2                                                 # not after get_order, not turn 3
    assert modes[1][0] is None and modes[3][0] is None and modes[4][0] is None


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


def test_confirmed_escalation_is_saved_once_with_only_real_evidence(monkeypatch):
    """The only write in the system: confirm -> one row; invented IDs dropped; a repeat finds the row."""
    from types import SimpleNamespace
    from orchestrator.tools import escalation

    saved, existing = [], []
    monkeypatch.setattr(escalation, "_ensure_table", lambda: None)
    monkeypatch.setattr(escalation, "query_rows", lambda *a, **k: list(existing))
    monkeypatch.setattr(escalation, "bigquery_client", lambda: SimpleNamespace(
        load_table_from_json=lambda rows, table, job_config: (saved.extend(rows), existing.extend(rows),
                                                              SimpleNamespace(result=lambda timeout=None: None))[-1]))

    def escalate(request):
        order_ev = last_responses(request)["get_order"]["evidence_id"]
        return call("escalate_case", order_id="ORD-78421", owner_team="Logistics Operations",
                    summary="Order and carrier disagree.", check_next=["handover scan"],
                    evidence_ids=[order_ev, "EV-CAR-ORD-78421-abcdef"])(request)

    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"), escalate,
                                    say("OUTCOME: escalate\nCAUSE: none\nFULFILABLE: not_applicable\nANSWER: saved")])

    async def go():
        s = await _session(rt)
        first = await rt.run_turn("analyst_test", s.id, "ORD-78421 says shipped. Is it on its way?")
        second = await rt.confirm("analyst_test", s.id, first.pending_confirmation["request_id"], True)
        return first, second

    first, second = run(go())
    assert len(saved) == 1 and saved[0]["order_id"] == "ORD-78421" and saved[0]["status"] == "open"
    assert saved[0]["evidence_ids"] == [first.trace["evidence_ids"][0]]      # the invented carrier ID is dropped
    assert saved[0]["correlation_id"] == second.correlation_id
    assert [t["outcome"] for t in second.trace["tools"]] == ["ok"]
    assert second.header["outcome"] == "escalate"


def test_escalation_for_another_order_is_refused(monkeypatch):
    from orchestrator.tools import escalation
    monkeypatch.setattr(escalation, "_ensure_table", lambda: (_ for _ in ()).throw(AssertionError("no write")))
    from types import SimpleNamespace
    ctx = SimpleNamespace(state={"current_order_id": "ORD-78421"}, session=SimpleNamespace(id="s1"),
                          run_config=None, user_id="u1")
    out = escalation.escalate_case("ORD-78465", "Logistics Operations", "x", ["y"], [], ctx)
    assert out["error_type"] == "invalid_argument" and "investigating ORD-78421" in out["message"]


def test_follow_up_citation_survives_the_sqlite_session_store(monkeypatch, tmp_path):
    """Same as the follow-up test, on the store the app really uses (state round-trips through SQLite)."""
    from google.adk.sessions import DatabaseSessionService

    def cite_first_turn(request):
        return "OUTCOME: answer\nCAUSE: none\nFULFILABLE: not_applicable\nANSWER: as before [EV-ORD-ORD-78421-" \
            + _order_suffix() + "]"

    db = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"), say("OUTCOME: check_next"),
                                    say(cite_first_turn)], session_service=db)

    async def go():
        s = await _session(rt)
        await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")
        return await rt.run_turn("analyst_test", s.id, "And what was its status again?")

    second = run(go())
    assert second.trace["invalid_citations"] == []


def test_a_hung_call_is_stopped_at_the_request_deadline(monkeypatch):
    from common import config as cfg
    from fakes import HangingModel

    rt = make_runtime(monkeypatch, [say("unused")])
    rt.app.root_agent.model = HangingModel()
    monkeypatch.setattr(cfg, "REQUEST_DEADLINE_SECONDS", 1)

    async def go():
        s = await _session(rt)
        return await rt.run_turn("analyst_test", s.id, "Investigate ORD-78421.")

    result = run(go())
    assert result.error == "deadline" and result.header["outcome"] == "partial"
    assert result.trace["termination"] == "REQUEST_DEADLINE_EXCEEDED"
    assert not rt.harness.active                                   # nothing left half-open


def test_second_message_on_a_busy_session_is_refused(monkeypatch):
    import asyncio as aio
    from orchestrator.runtime import SessionBusy
    rt = make_runtime(monkeypatch, [call("get_order", order_id="ORD-78421"), say("OUTCOME: check_next")])

    async def go():
        s = await _session(rt)
        rt._busy.add(s.id)                                         # as if the first message is still running
        try:
            await rt.run_turn("analyst_test", s.id, "again")
        except SessionBusy:
            return True
        return False

    assert run(go()) is True
