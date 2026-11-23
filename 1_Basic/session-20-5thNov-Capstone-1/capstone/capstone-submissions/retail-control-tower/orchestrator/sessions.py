"""Session service (session 17 services.py, Gate 8).

local_sqlite: ADK DatabaseSessionService on a SQLite file under output/.
Investigations survive a restart of the web app, and each analyst's sessions
are separate (sessions are keyed by app, user and session ID).

vertex: VertexAiSessionService on an Agent Engine (the production step).

No MemoryService: order and inventory data must always be read live, and
recalling old conclusions would bring back similarity-as-causality
(decision matrix: long-term memory = none).
"""

from __future__ import annotations

from common import config


def build_session_service():
    if config.SESSION_BACKEND == "vertex":
        from google.adk.sessions import VertexAiSessionService
        return VertexAiSessionService(project=config.PROJECT_ID, location=config.AGENT_ENGINE_LOCATION,
                                      agent_engine_id=config.VERTEX_AGENT_ENGINE_ID)

    from google.adk.sessions import DatabaseSessionService
    config.SESSION_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    return DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{config.SESSION_DB_FILE}")


def effective_app_name() -> str:
    """Vertex sessions are keyed by the Agent Engine resource; local sessions by our app name."""
    if config.SESSION_BACKEND == "vertex":
        return (f"projects/{config.PROJECT_ID}/locations/{config.AGENT_ENGINE_LOCATION}/"
                f"reasoningEngines/{config.VERTEX_AGENT_ENGINE_ID}")
    return config.APP_NAME
