"""One way to run the agent from a script (Step 8, D61): used by smoke_test.py,
src/05_run_demos.py and src/06_evaluate.py.

converse(["question", "follow-up"]) runs one conversation and returns, per turn:
the user text, the tool calls the agent made (name, arguments, call ID), the
final text the user would see, the full runtime result of each tool call (from
tools.TRACE, for the brief's trace), and the seconds the turn took.

Needs Google Cloud: the agent itself calls Gemini to route.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from google.adk.runners import InMemoryRunner  # noqa: E402
from google.genai import types  # noqa: E402

import tools  # noqa: E402
from medevidence_agent_vks.agent import root_agent  # noqa: E402


APP = "medevidence_scripts"


async def _turn(runner: InMemoryRunner, session_id: str, text: str) -> dict:
    tools.TRACE.clear()
    calls, final, t0 = [], "", time.perf_counter()
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(user_id="script", session_id=session_id, new_message=message):
        for call in event.get_function_calls():
            calls.append({"id": call.id, "name": call.name, "args": dict(call.args or {})})
        if event.is_final_response() and event.content and event.content.parts:
            final = "".join(p.text or "" for p in event.content.parts if not getattr(p, "thought", False))
    by_id = {t["call_id"]: t["result"] for t in tools.TRACE if t["call_id"]}
    for call in calls:  # pair each call with its full result (skipped calls have none)
        call["result"] = by_id.get(call["id"])
    for t in tools.TRACE:  # code-made actions with no model call (D53 layer 3: escalate by code)
        if not t["call_id"]:
            calls.append({"id": None, "name": t.get("tool", "code"), "args": {}, "result": t["result"]})
    return {"user": text, "calls": calls, "final": final.strip(), "seconds": round(time.perf_counter() - t0, 1)}


async def _conversation(turns: list[str]) -> list[dict]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP)
    session = await runner.session_service.create_session(app_name=APP, user_id="script")
    return [await _turn(runner, session.id, text) for text in turns]


# One event loop for the whole script: asyncio.run() per conversation closed the loop while
# Gemini's async HTTP clients were still open ("Event loop is closed" tracebacks at exit).
_LOOP = asyncio.new_event_loop()


def converse(turns: list[str]) -> list[dict]:
    """Run one conversation (a fresh session) and return its turns."""
    return _LOOP.run_until_complete(_conversation(turns))


def describe_call(call: dict) -> str:
    """'search_current(country='Germany')': the routing, without the question text."""
    args = ", ".join(f"{k}={v!r}" for k, v in call["args"].items() if k != "question")
    return f"{call['name']}({args})"
