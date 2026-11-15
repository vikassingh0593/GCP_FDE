from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config import settings
from app.identity import build_user_id, normalize_email
from app.runtime import (
    create_session,
    get_session,
    list_sessions,
    run_turn,
    runtime,
    save_session_to_memory,
)

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "web" / "static"

api = FastAPI(title="FDE-1 Partner GPC", version="1.0.0")

class IdentityRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)


class SessionRequest(BaseModel):
    user_id: str = Field(min_length=1)
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)


class MemoryRequest(BaseModel):
    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)





@api.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return human-readable JSON instead of nested validation objects."""
    messages = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc", [])[1:])
        message = error.get("msg", "Invalid request")
        messages.append(f"{field}: {message}" if field else message)
    return JSONResponse(
        status_code=422,
        content={"detail": "; ".join(messages) or "Invalid request."},
    )


@api.exception_handler(Exception)
async def unhandled_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Keep unexpected failures JSON-safe for the teaching UI."""
    LOGGER.exception("Unhandled request failure: %s", exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                "Server operation failed. Check the terminal traceback. "
                f"{type(exc).__name__}: {exc}"
            )
        },
    )



def safe_state(state) -> dict:
    """Return persisted Session state with training email masked."""
    result = dict(state or {})
    if "user:email" in result:
        result["user:email"] = "***masked***"
    return result

def session_view(session) -> dict:
    """Serialize teaching-relevant Session properties only."""
    return {
        "session_id": session.id,
        "user_id": session.user_id,
        "state": safe_state(session.state),
        "event_count": len(session.events or []),
        "last_update_time": session.last_update_time,
    }



async def require_session(user_id: str, session_id: str):
    """Resolve a session in the supplied user scope or return a clean 404."""
    session = await get_session(user_id, session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Session not found for this user. Identify the user and "
                "create/select a session before chatting."
            ),
        )
    return session



@api.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

@api.post("/api/identify")
async def identify(payload: IdentityRequest):
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user_id = build_user_id(email)
    sessions = await list_sessions(user_id)
    return {
        "user_id": user_id,
        "full_name": payload.full_name.strip(),
        "email": email,
        "sessions": [session_view(item) for item in sessions],
        "warning": "Training identity only: email is not authenticated.",
    }


@api.post("/api/sessions")
async def new_session(payload: SessionRequest):
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    expected_user_id = build_user_id(email)
    if payload.user_id != expected_user_id:
        raise HTTPException(status_code=400, detail="Identity mismatch.")

    session = await create_session(
        payload.user_id,
        payload.full_name,
        email,
    )
    return session_view(session)


@api.get("/api/users/{user_id}/sessions")
async def sessions_for_user(user_id: str):
    sessions = await list_sessions(user_id)
    return {"sessions": [session_view(item) for item in sessions]}


@api.get("/api/users/{user_id}/sessions/{session_id}")
async def inspect_session(user_id: str, session_id: str):
    return session_view(await require_session(user_id, session_id))



@api.post("/api/chat")
async def chat(payload: ChatRequest):
    await require_session(payload.user_id, payload.session_id)
    answer = await run_turn(
        payload.user_id,
        payload.session_id,
        payload.message.strip(),
    )
    updated = await require_session(payload.user_id, payload.session_id)
    return {"answer": answer, "session": session_view(updated)}


@api.post("/api/memory/save")
async def remember(payload: MemoryRequest):
    await require_session(payload.user_id, payload.session_id)
    await save_session_to_memory(payload.user_id, payload.session_id)
    return {
        "status": "saved",
        "memory_backend": settings.memory_backend,
        "message": (
            "Session submitted to ADK MemoryService. Start a NEW session "
            "for the same user and ask about the earlier conversation."
        ),
    }


@api.get("/api/runtime")
async def runtime_info():
    return {
        "app_name": runtime.app_name,
        "session_backend": settings.session_backend,
        "memory_backend": settings.memory_backend,
        "model": settings.model_id,
        "identity": "training-only; no authentication",
    }
