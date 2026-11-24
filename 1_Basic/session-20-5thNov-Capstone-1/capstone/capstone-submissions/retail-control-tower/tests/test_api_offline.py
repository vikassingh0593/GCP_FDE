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
    body = r.json()
    return body["user_id"], {"X-Analyst-Token": body["token"]}


def test_page_and_runtime(client):
    assert client.get("/").status_code == 200
    info = client.get("/api/runtime").json()
    assert info["specialist_reachable"] is False and "not authentication" in info["identity"]


def test_identity_is_pseudonymous_and_stable(client):
    (a1, _), (a2, _) = _sign_in(client, "Asha@Example.com "), _sign_in(client, "asha@example.com")
    assert a1 == a2 and a1.startswith("analyst_") and "asha" not in a1


def test_chat_returns_answer_header_and_trace(client):
    _, auth = _sign_in(client, "asha@example.com")
    session = client.post("/api/sessions", headers=auth).json()
    r = client.post("/api/chat", headers=auth, json={"session_id": session["session_id"],
                                                     "message": "Investigate ORD-78421."}).json()
    assert r["header"]["outcome"] == "check_next"
    assert r["trace"]["correlation_id"] == r["correlation_id"]
    assert r["session"]["state"]["current_order_id"] == "ORD-78421"
    replay = client.get(f"/api/sessions/{session['session_id']}", headers=auth).json()
    assert [t["role"] for t in replay["transcript"]] == ["analyst", "agent"]


def test_another_analyst_cannot_open_or_post_into_the_session(client):
    _, asha = _sign_in(client, "asha@example.com")
    _, ravi = _sign_in(client, "ravi@example.com")
    session = client.post("/api/sessions", headers=asha).json()
    assert client.get(f"/api/sessions/{session['session_id']}", headers=ravi).status_code == 404
    r = client.post("/api/chat", headers=ravi, json={"session_id": session["session_id"], "message": "hi"})
    assert r.status_code == 404
    assert session["session_id"] not in str(client.get("/api/sessions", headers=ravi).json())


def test_every_endpoint_needs_a_valid_token(client):
    """Knowing an analyst ID (it is in logs and traces) is not enough: the API takes it from the signed token."""
    user, asha = _sign_in(client, "asha@example.com")
    session = client.post("/api/sessions", headers=asha).json()
    forged = {"X-Analyst-Token": f"{user}.9999999999.{'0' * 32}"}
    for headers in ({}, forged):
        assert client.get("/api/sessions", headers=headers).status_code == 401
        assert client.post("/api/sessions", headers=headers).status_code == 401
        assert client.get(f"/api/sessions/{session['session_id']}", headers=headers).status_code == 401
        assert client.post("/api/chat", headers=headers,
                           json={"session_id": session["session_id"], "message": "hi"}).status_code == 401


def test_tokens_expire():
    from orchestrator.identity import issue_token, verify_token
    token = issue_token("analyst_x", now=1000)
    assert verify_token(token, now=1001) == "analyst_x"
    assert verify_token(token, now=1000 + 13 * 3600) is None
