"""web/api.py with a scripted runtime: identity, sessions per analyst, chat, isolation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from google.adk.sessions import InMemorySessionService

from fakes import ORDER_ROWS, ScriptedModel, call, fake_query_rows, say


@pytest.fixture()
def client(monkeypatch):
    from orchestrator import runtime as runtime_module
    from orchestrator.tools import orders
    from web import api

    monkeypatch.setattr(orders, "query_rows", fake_query_rows({"orders": list(ORDER_ROWS.values())}))
    rt = runtime_module.Runtime(card_url="http://127.0.0.1:9/.well-known/agent-card.json", timeout=2,
                                session_service=InMemorySessionService())
    rt.app.root_agent.model = ScriptedModel(steps=[
        call("get_order", order_id="ORD-78421"),
        say("OUTCOME: check_next\nCAUSE: none\nFULFILABLE: unknown\nANSWER: Looked up the order."),
    ])
    api.set_runtime(rt)

    async def no_specialist():
        return False
    monkeypatch.setattr(runtime_module, "specialist_reachable", no_specialist)
    yield TestClient(api.api)
    api.set_runtime(None)


def _sign_in(client, email):
    r = client.post("/api/identify", json={"full_name": "Asha Verma", "email": email})
    assert r.status_code == 200
    return r.json()["user_id"]


def test_page_and_runtime(client):
    assert client.get("/").status_code == 200
    info = client.get("/api/runtime").json()
    assert info["specialist_reachable"] is False and "not authentication" in info["identity"]


def test_identity_is_pseudonymous_and_stable(client):
    a1, a2 = _sign_in(client, "Asha@Example.com "), _sign_in(client, "asha@example.com")
    assert a1 == a2 and a1.startswith("analyst_") and "asha" not in a1


def test_chat_returns_answer_header_and_trace(client):
    user = _sign_in(client, "asha@example.com")
    session = client.post("/api/sessions", json={"user_id": user, "email": "asha@example.com"}).json()
    r = client.post("/api/chat", json={"user_id": user, "session_id": session["session_id"],
                                       "message": "Investigate ORD-78421."}).json()
    assert r["header"]["outcome"] == "check_next"
    assert r["trace"]["correlation_id"] == r["correlation_id"]
    assert r["session"]["state"]["current_order_id"] == "ORD-78421"
    replay = client.get(f"/api/users/{user}/sessions/{session['session_id']}").json()
    assert [t["role"] for t in replay["transcript"]] == ["analyst", "agent"]


def test_another_analyst_cannot_open_the_session(client):
    asha = _sign_in(client, "asha@example.com")
    ravi = _sign_in(client, "ravi@example.com")
    session = client.post("/api/sessions", json={"user_id": asha, "email": "asha@example.com"}).json()
    assert client.get(f"/api/users/{ravi}/sessions/{session['session_id']}").status_code == 404
    r = client.post("/api/chat", json={"user_id": ravi, "session_id": session["session_id"], "message": "hi"})
    assert r.status_code == 404


def test_session_creation_checks_identity(client):
    asha = _sign_in(client, "asha@example.com")
    r = client.post("/api/sessions", json={"user_id": asha, "email": "ravi@example.com"})
    assert r.status_code == 400
