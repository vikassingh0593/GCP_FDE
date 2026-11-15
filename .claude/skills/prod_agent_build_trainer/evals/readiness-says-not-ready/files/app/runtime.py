from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4


from google.adk.runners import Runner
from google.genai.types import Content, Part

from app.agent import root_agent
from app.services import (
    build_memory_service,
    build_session_service,
    effective_app_name,
)



@dataclass
class RuntimeServices:
    """Shared services must live for the lifetime of the web process."""

    session_service: Any
    memory_service: Any
    runner: Runner
    app_name: str

def build_runtime() -> RuntimeServices:

    session_service = build_session_service()
    memory_service = build_memory_service()
    app_name = effective_app_name()

    runner = Runner(
        agent=root_agent,
        app_name = app_name,
        session_service=session_service,
        memory_service=memory_service,
    )

    return RuntimeServices(
        session_service=session_service,
        memory_service=memory_service,
        runner=runner,
        app_name=app_name,
    )


runtime = build_runtime()


async def create_session(
        user_id: str,
        full_name: str,
        email: str) -> Any:

    session_id = f"s_{uuid4().hex[:16]}"

    initial_state = {
        "user:name": full_name,
        "user:email": email,
        "app:lab_topic": "ADK session, state, and memory demonstration",
        "current_case": "not-set"
    }

    return await runtime.session_service.create_session(
        app_name=runtime.app_name,
        user_id=user_id,
        session_id=session_id,
        state=initial_state,
    )


async def get_session(user_id: str, session_id: str) -> Any:

    return await runtime.session_service.get_session(
        app_name=runtime.app_name,
        user_id=user_id,
        session_id=session_id,
    )

async def list_sessions(user_id: str) -> list[Any]:
    """List conversation threads for one user."""
    response = await runtime.session_service.list_sessions(
        app_name=runtime.app_name,
        user_id=user_id,
    )
    return list(response.sessions)


async def run_turn(
        user_id: str,
        session_id: str,
        text: str
) -> str:

    message = Content(
        role= "user",
        parts=[Part(text=text)]
    )

    final_text = ""

    async for event in runtime.runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(
                part.text or "" for part in event.content.parts
            ).strip()

    return final_text or "(Agent produced no final text response.)"


async def save_session_to_memory(user_id: str, session_id: str) -> None:

    session = await get_session(user_id=user_id, session_id=session_id)

    if session is None:
        raise ValueError(f"Session not found for user_id={user_id}, session_id={session_id}")

    await runtime.memory_service.add_session_to_memory(session)
