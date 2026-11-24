"""FastAPI app: the analyst's web experience (session 17 api.py, for the control tower).

Endpoints:
    GET  /                                        the page (web/static/index.html)
    GET  /api/runtime                             models, session backend, specialist status
    POST /api/identify                            training identity -> analyst ID, signed token, sessions
    POST /api/sessions                            new investigation session
    GET  /api/sessions                            the analyst's sessions
    GET  /api/sessions/{sid}                      one session: state (masked) and transcript
    POST /api/chat                                one analyst message -> answer + trace summary
    POST /api/confirm                             confirm or decline a pending escalation

Every endpoint after /api/identify needs the X-Analyst-Token header, and takes
the analyst from that signed token, never from the request body or URL (the
analyst ID is not a secret: it is in logs and traces). Sessions are looked up
in that analyst's scope only: another analyst's session ID returns 404, never
its content (session isolation, Gate 8).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common import config
from common.masking import mask
from orchestrator.identity import build_user_id, issue_token, normalize_email, verify_token
from orchestrator.runtime import SessionBusy

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


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)


class ConfirmRequest(BaseModel):
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


@api.exception_handler(SessionBusy)
async def busy_handler(request: Request, exc: SessionBusy) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "This investigation is still answering your previous "
                                                            "message. Wait for it, then ask again."})


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


def analyst(x_analyst_token: str | None = Header(default=None)) -> str:
    """The calling analyst, from the signed token. Missing, forged or expired -> 401."""
    user_id = verify_token(x_analyst_token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Sign in again: missing or expired analyst token.")
    return user_id


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
    return {"user_id": user_id, "token": issue_token(user_id), "display_name": payload.full_name.strip().split()[0],
            "sessions": [session_view(s) for s in sessions],
            "warning": "Training identity only: the email is not authenticated."}


@api.post("/api/sessions")
async def new_session(user_id: str = Depends(analyst)):
    return session_view(await runtime().create_session(user_id))


@api.get("/api/sessions")
async def my_sessions(user_id: str = Depends(analyst)):
    return {"sessions": [session_view(s) for s in await runtime().list_sessions(user_id)]}


@api.get("/api/sessions/{session_id}")
async def inspect_session(session_id: str, user_id: str = Depends(analyst)):
    session = await require_session(user_id, session_id)
    return {**session_view(session), "transcript": runtime().transcript(session)}


@api.post("/api/chat")
async def chat(payload: ChatRequest, user_id: str = Depends(analyst)):
    await require_session(user_id, payload.session_id)
    result = await runtime().run_turn(user_id, payload.session_id, payload.message.strip())
    updated = await require_session(user_id, payload.session_id)
    return {**result.to_dict(), "session": session_view(updated)}


@api.post("/api/confirm")
async def confirm(payload: ConfirmRequest, user_id: str = Depends(analyst)):
    await require_session(user_id, payload.session_id)
    result = await runtime().confirm(user_id, payload.session_id, payload.request_id, payload.confirmed)
    updated = await require_session(user_id, payload.session_id)
    return {**result.to_dict(), "session": session_view(updated)}
