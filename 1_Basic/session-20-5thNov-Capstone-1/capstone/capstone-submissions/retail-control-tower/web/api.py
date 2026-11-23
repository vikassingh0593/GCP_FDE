"""FastAPI app: the analyst's web experience (session 17 api.py, for the control tower).

Endpoints:
    GET  /                                        the page (web/static/index.html)
    GET  /api/runtime                             models, session backend, specialist status
    POST /api/identify                            training identity -> pseudonymous analyst ID + sessions
    POST /api/sessions                            new investigation session
    GET  /api/users/{user_id}/sessions            the analyst's sessions
    GET  /api/users/{user_id}/sessions/{sid}      one session: state (masked) and transcript
    POST /api/chat                                one analyst message -> answer + trace summary
    POST /api/confirm                             confirm or decline a pending escalation

Every session lookup is scoped to the analyst's user ID: another analyst's
session ID returns 404, never its content (session isolation, Gate 8).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common import config
from common.masking import mask
from orchestrator.identity import build_user_id, normalize_email

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

api = FastAPI(title="Retail Order Exception Control Tower", version="1.0.0")
api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_runtime = None


def runtime():
    """Built on first use, so importing the API (tests, tooling) needs no cloud."""
    global _runtime
    if _runtime is None:
        from orchestrator.runtime import Runtime
        _runtime = Runtime()
    return _runtime


def set_runtime(value) -> None:
    """Tests swap in a runtime with a scripted model."""
    global _runtime
    _runtime = value


class IdentityRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)


class SessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=5, max_length=200)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class ConfirmRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    session_id: str = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=1, max_length=200)
    confirmed: bool


@api.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    messages = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error.get("loc", [])[1:])
        messages.append(f"{field}: {error.get('msg', 'invalid')}" if field else error.get("msg", "invalid"))
    return JSONResponse(status_code=422, content={"detail": "; ".join(messages) or "Invalid request."})


@api.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled request failure: %s", exc)
    return JSONResponse(status_code=500, content={"detail": f"Server error ({type(exc).__name__}). "
                                                            "Check the terminal running the web app."})


def session_view(session) -> dict:
    return {"session_id": session.id, "user_id": session.user_id, "state": mask(dict(session.state or {})),
            "event_count": len(session.events or []), "last_update_time": session.last_update_time}


async def require_session(user_id: str, session_id: str):
    session = await runtime().get_session(user_id, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found for this analyst.")
    return session


def _check_identity(user_id: str, email: str) -> None:
    try:
        expected = build_user_id(email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if user_id != expected:
        raise HTTPException(status_code=400, detail="Identity mismatch.")


@api.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@api.get("/api/runtime")
async def runtime_info():
    from orchestrator.runtime import specialist_reachable
    return {"app_name": config.APP_NAME, "session_backend": config.SESSION_BACKEND,
            "orchestrator_model": config.ORCHESTRATOR_MODEL, "specialist_model": config.SPECIALIST_MODEL,
            "specialist_card": config.FULFILMENT_AGENT_CARD_URL, "specialist_reachable": await specialist_reachable(),
            "identity": "training identity only; not authentication", "environment": config.LAB_ENVIRONMENT}


@api.post("/api/identify")
async def identify(payload: IdentityRequest):
    try:
        email = normalize_email(payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user_id = build_user_id(email)
    sessions = await runtime().list_sessions(user_id)
    return {"user_id": user_id, "display_name": payload.full_name.strip().split()[0],
            "sessions": [session_view(s) for s in sessions],
            "warning": "Training identity only: the email is not authenticated."}


@api.post("/api/sessions")
async def new_session(payload: SessionRequest):
    _check_identity(payload.user_id, payload.email)
    return session_view(await runtime().create_session(payload.user_id))


@api.get("/api/users/{user_id}/sessions")
async def sessions_for_user(user_id: str):
    return {"sessions": [session_view(s) for s in await runtime().list_sessions(user_id)]}


@api.get("/api/users/{user_id}/sessions/{session_id}")
async def inspect_session(user_id: str, session_id: str):
    session = await require_session(user_id, session_id)
    return {**session_view(session), "transcript": runtime().transcript(session)}


@api.post("/api/chat")
async def chat(payload: ChatRequest):
    await require_session(payload.user_id, payload.session_id)
    result = await runtime().run_turn(payload.user_id, payload.session_id, payload.message.strip())
    updated = await require_session(payload.user_id, payload.session_id)
    return {**result.to_dict(), "session": session_view(updated)}


@api.post("/api/confirm")
async def confirm(payload: ConfirmRequest):
    await require_session(payload.user_id, payload.session_id)
    result = await runtime().confirm(payload.user_id, payload.session_id, payload.request_id, payload.confirmed)
    updated = await require_session(payload.user_id, payload.session_id)
    return {**result.to_dict(), "session": session_view(updated)}
