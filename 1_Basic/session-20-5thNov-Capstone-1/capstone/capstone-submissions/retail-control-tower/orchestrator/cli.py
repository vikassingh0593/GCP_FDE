"""Terminal runner for debugging (session 13 02_enterprise_runner.py).

Streams tool calls and the answer, then prints the invocation report, so you
can see exactly what the orchestrator did. Use this instead of `adk web`: the
harness refuses requests without a correlation ID, and this runner sends one.

Run from retail-control-tower/ (start the specialist first for fulfilment checks):

    python -m orchestrator.cli                                  # interactive, one session
    python -m orchestrator.cli -q "Investigate ORD-78421."      # one question, then exit

Type `exit` to stop.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from common.harness import render_report
from common.harness.logs import configure_stdlib_logging
from orchestrator.identity import build_user_id
from orchestrator.runtime import Runtime


def print_event(event) -> None:
    for call in event.get_function_calls() or []:
        print(f"\n[FUNCTION CALL] {call.name} {json.dumps(dict(call.args or {}), default=str)[:300]}")
    for response in event.get_function_responses() or []:
        body = response.response or {}
        print(f"[FUNCTION RESPONSE] {response.name} status={body.get('status')} "
              f"freshness={body.get('freshness')} evidence={body.get('evidence_id')}")


async def ask(runtime: Runtime, user_id: str, session_id: str, question: str) -> None:
    result = await runtime.run_turn(user_id, session_id, question, on_event=print_event)
    while result.pending_confirmation:
        p = result.pending_confirmation
        print(f"\n[CONFIRMATION NEEDED] {p['tool']}: {json.dumps(p['args'], indent=2)}")
        yes = input("Save this escalation? [y/N] ").strip().lower() == "y"
        result = await runtime.confirm(user_id, session_id, p["request_id"], yes, on_event=print_event)
    print(f"\n[orchestrator]\n{result.answer}")
    for warning in result.warnings:
        print(f"WARNING: {warning}")
    if result.trace:
        print(render_report(result.trace))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal runner for the Order Exception Orchestrator.")
    parser.add_argument("-q", "--question", help="ask one question and exit")
    parser.add_argument("--analyst", default="cli.analyst@example.com", help="analyst email (training identity)")
    args = parser.parse_args()

    configure_stdlib_logging()
    runtime = Runtime()
    user_id = build_user_id(args.analyst)
    session = await runtime.create_session(user_id)
    print(f"\nORDER EXCEPTION CONTROL TOWER (terminal)\n{'=' * 60}\nUser: {user_id}  Session: {session.id}")

    if args.question:
        await ask(runtime, user_id, session.id, args.question)
        return
    print("Type `exit` to stop.")
    while True:
        question = input("\nQuestion:\n> ").strip()
        if question.lower() in {"exit", "quit"}:
            return
        if question:
            await ask(runtime, user_id, session.id, question)


if __name__ == "__main__":
    asyncio.run(main())
