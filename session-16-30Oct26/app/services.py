from __future__ import annotations

from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import (
    DatabaseSessionService,
    InMemorySessionService,
    VertexAiSessionService,
)


from app.config import settings


def build_session_service():
    backend = settings.session_backend.lower()

    if backend == "in_memory":
        return InMemorySessionService()

    if backend == "local_sqlite":
        settings.session_db_path.parent.mkdir(parents=True, exist_ok=True)
        return DatabaseSessionService(db_url=settings.session_db_url)

    if backend == "vertex":
        return VertexAiSessionService(
            project=settings.agent_platform_project,
            location=settings.agent_platform_location,
        )


def build_memory_service():
    backend = settings.memory_backend.lower()

    if backend == "in_memory":
        return InMemoryMemoryService()

    if backend == "memory_bank":
        from google.adk.memory import VertexAiMemoryBankService

        return VertexAiMemoryBankService(
            project=settings.memory_bank_project,
            location=settings.memory_bank_location,
            agent_engine_id=settings.memory_bank_agent_engine_id,
        )


def effective_app_name() -> str:

    if settings.session_backend.lower()=="vertex":
        return  settings.app_name

    if settings.agent_engine_resource_name:
        return settings.agent_engine_resource_name


    return (
        f"projects/{settings.agent_platform_project}/locations/"
        f"{settings.agent_platform_location}/reasoningEngines/"
        f"{settings.agent_engine_id}"
    )