"""
Interactive enterprise ADK runner.

This is the primary Day-1 demonstration. It binds trusted request metadata and an
InvocationTrace, executes one ADK invocation, streams events, then renders the
runtime report.

Type `exit` to stop.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent import root_agent  # noqa: E402
from app.harness.context import create_request_context  # noqa: E402
from app.harness.policy import ExecutionPolicy  # noqa: E402
from app.harness.registry import REGISTRY  # noqa: E402
from app.harness.report import render_report  # noqa: E402
from app.harness.trace import InvocationTrace  # noqa: E402


APP_NAME = "app"


def event_text(event: Any) -> str:
    """Extract readable text from a streamed ADK event."""
    content = getattr(event, "content", None)

    if content is None:
        return ""

    return "\n".join(
        part.text
        for part in getattr(content, "parts", [])
        if getattr(part, "text", None)
    )


async def main() -> None:
    """Run repeated invocations inside one in-memory session."""
    session_service = InMemorySessionService()
    session_id = f"enterprise-day1-{uuid.uuid4().hex[:8]}"
    user_id = "fde-user-101"

    await session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
        session_id=session_id,
    )

    runner = Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    print("\nENTERPRISE ADK RUNTIME HARNESS")
    print("=" * 60)
    print("Session:", session_id)
    print("Type `exit` to stop.")

    while True:
        prompt = input("\nIncident request:\n> ").strip()

        if prompt.lower() in {"exit", "quit"}:
            return

        if not prompt:
            print("Prompt cannot be empty.")
            continue

        request = create_request_context()
        trace = InvocationTrace(
            request=request,
            policy=ExecutionPolicy.from_environment(),
        )
        trace.add_event(
            "REQUEST_ACCEPTED",
            correlation_id=request.correlation_id,
            tenant=request.tenant_id,
        )

        token = REGISTRY.bind(trace)

        try:
            message = types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            )

            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
            ):
                author = getattr(event, "author", "unknown")
                trace.add_event("ADK_EVENT", author=author)

                calls_getter = getattr(event, "get_function_calls", None)
                if callable(calls_getter):
                    for call in calls_getter() or []:
                        print(
                            f"\n[FUNCTION CALL] {call.name} "
                            f"{dict(call.args)}"
                        )

                responses_getter = getattr(
                    event,
                    "get_function_responses",
                    None,
                )
                if callable(responses_getter):
                    for response in responses_getter() or []:
                        print(
                            f"[FUNCTION RESPONSE] {response.name} "
                            f"{response.response}"
                        )

                text = event_text(event)
                if text:
                    print(f"\n[{author}]")
                    print(text)

            if trace.termination_reason == "RUNNING":
                trace.finish("NORMAL")
            else:
                trace.finish(trace.termination_reason)

        except Exception as exc:
            trace.add_event(
                "UNHANDLED_RUNTIME_ERROR",
                error_type=type(exc).__name__,
                message=str(exc),
            )
            trace.finish("UNHANDLED_RUNTIME_ERROR")
            raise

        finally:
            print(render_report(trace))
            REGISTRY.reset(token)


if __name__ == "__main__":
    asyncio.run(main())
