"""Runtime services for the orchestrator (session 17 runtime.py + session 13 runner).

One Runtime per process: the Runner, the session service and the harness live
as long as the web app. For every analyst message it:

1. creates a trusted RequestContext (new correlation ID, the analyst's
   pseudonymous ID, the session) and passes it in RunConfig.custom_metadata,
   where the harness and the A2A client read it;
2. runs one invocation and collects the final answer, any pending
   confirmation (escalate_case) and the harness trace row;
3. turns an unexpected failure into a controlled message with the
   correlation ID, never a stack trace and never a guessed answer.

Used by web/api.py, orchestrator/cli.py and evals/run_evals.py.
"""

from __future__ import annotations

import asyncio
import re
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from google.adk.agents.run_config import RunConfig, ToolThreadPoolConfig
from google.adk.runners import Runner
from google.genai import types

from common import config
from common.harness import REFUSAL_PREFIX, RequestContext
from common.harness.logs import log_event
from orchestrator import answer_guard
from orchestrator.sessions import build_session_service, effective_app_name

CONFIRMATION_CALL = "adk_request_confirmation"
# The tools are plain functions that wait on BigQuery and Vertex AI. Without a pool, ADK runs them on the
# event loop, and one slow query freezes the web app for every analyst. 8 workers per process.
TOOL_THREADS = 8
HEADER = re.compile(r"^\s*(OUTCOME|CAUSE|FULFILABLE)\s*:\s*([A-Za-z_]+)", re.M)


def parse_header(answer: str) -> dict:
    """{'outcome': ..., 'cause': ..., 'fulfilable': ...} from the fixed answer format (None if missing)."""
    found = {k.lower(): v.strip().lower() for k, v in HEADER.findall(answer or "")}
    return {k: found.get(k) for k in ("outcome", "cause", "fulfilable")}


class SessionBusy(Exception):
    """A second message arrived while this session is still answering the first (two tabs, double submit)."""


@dataclass
class TurnResult:
    answer: str
    correlation_id: str
    header: dict = field(default_factory=dict)
    pending_confirmation: dict | None = None
    trace: dict | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Runtime:
    def __init__(self, card_url: str | None = None, timeout: float | None = None, session_service=None):
        from orchestrator.order_exception_agent import agent as orchestrator_agent

        if card_url or timeout:
            self.app, self.harness = orchestrator_agent.build_app(card_url, timeout)
        else:
            self.app, self.harness = orchestrator_agent.app, orchestrator_agent.HARNESS
        self.session_service = session_service or build_session_service()
        self.app_name = effective_app_name()
        self.runner = Runner(app=self.app, app_name=self.app_name, session_service=self.session_service)
        # Confirmation request ID -> correlation ID of the run that asked for it, so the resumed run
        # is logged with that run as its parent. In memory: after a restart the link is simply absent.
        self._paused: dict[str, str] = {}
        # One investigation at a time per session: two runs on one session would interleave their events.
        self._busy: set[str] = set()

    # ------------------------------------------------------------------ sessions

    async def create_session(self, user_id: str) -> Any:
        return await self.session_service.create_session(
            app_name=self.app_name, user_id=user_id, session_id=f"s_{uuid.uuid4().hex[:16]}", state={})

    async def get_session(self, user_id: str, session_id: str) -> Any:
        return await self.session_service.get_session(app_name=self.app_name, user_id=user_id, session_id=session_id)

    async def list_sessions(self, user_id: str) -> list[Any]:
        response = await self.session_service.list_sessions(app_name=self.app_name, user_id=user_id)
        return list(response.sessions)

    @staticmethod
    def transcript(session) -> list[dict]:
        """User messages and final agent answers, for replaying a session in the UI."""
        turns = []
        for event in session.events or []:
            parts = (event.content.parts if event.content else None) or []
            text = "".join(p.text or "" for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
            if not text.strip() or any(getattr(p, "function_call", None) for p in parts):
                continue
            turns.append({"role": "analyst" if event.author == "user" else "agent", "text": text.strip()})
        return turns

    # ------------------------------------------------------------------ turns

    async def run_turn(self, user_id: str, session_id: str, text: str,
                       on_event: Callable[[Any], None] | None = None) -> TurnResult:
        message = types.Content(role="user", parts=[types.Part(text=text)])
        return await self._run(user_id, session_id, message, on_event)

    async def confirm(self, user_id: str, session_id: str, request_id: str, confirmed: bool,
                      on_event: Callable[[Any], None] | None = None) -> TurnResult:
        """The analyst's answer to a pending confirmation (escalate_case): resumes the paused run."""
        message = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
            id=request_id, name=CONFIRMATION_CALL, response={"confirmed": bool(confirmed)}))])
        return await self._run(user_id, session_id, message, on_event, parent=self._paused.pop(request_id, None))

    async def _run(self, user_id: str, session_id: str, message: types.Content,
                   on_event: Callable[[Any], None] | None, parent: str | None = None) -> TurnResult:
        request = RequestContext.create(user=user_id, session_id=session_id, parent_correlation_id=parent)
        run_config = RunConfig(custom_metadata=request.to_metadata(),
                               max_llm_calls=config.MAX_MODEL_CALLS_PER_INVOCATION + 2,   # harness stops first
                               tool_thread_pool_config=ToolThreadPoolConfig(max_workers=TOOL_THREADS))
        if session_id in self._busy:
            raise SessionBusy(session_id)
        self._busy.add(session_id)
        seen = {"answer": "", "pending": None, "errors": []}

        async def consume() -> None:
            async for event in self.runner.run_async(user_id=user_id, session_id=session_id,
                                                     new_message=message, run_config=run_config):
                if on_event:
                    on_event(event)
                if event.error_message:
                    seen["errors"].append(event.error_message)
                for call in event.get_function_calls() or []:
                    if call.name == CONFIRMATION_CALL:
                        original = (call.args or {}).get("originalFunctionCall", {})
                        seen["pending"] = {"request_id": call.id, "tool": original.get("name"),
                                           "args": original.get("args", {}),
                                           "hint": (call.args or {}).get("toolConfirmation", {}).get("hint", "")}
                if event.content and event.content.parts and not event.partial and event.author != "user":
                    text = "".join(p.text or "" for p in event.content.parts
                                   if getattr(p, "text", None) and not getattr(p, "thought", False))
                    if text.strip() and not event.get_function_calls():
                        seen["answer"] = text.strip()

        try:
            await asyncio.wait_for(consume(), timeout=config.REQUEST_DEADLINE_SECONDS)
        except asyncio.TimeoutError:
            # A call hung past the hard deadline: stop, close the trace, and say so. Nothing is concluded.
            self.harness.abandon(request.correlation_id, "REQUEST_DEADLINE_EXCEEDED")
            log_event("orchestrator", "turn_deadline", correlation_id=request.correlation_id, level="ERROR",
                      deadline_s=config.REQUEST_DEADLINE_SECONDS)
            answer = (f"OUTCOME: partial\nCAUSE: none\nFULFILABLE: unknown\n"
                      f"ANSWER: The investigation did not finish within {config.REQUEST_DEADLINE_SECONDS} s and was "
                      f"stopped. Nothing was concluded. Try again, or escalate with correlation ID "
                      f"{request.correlation_id}.")
            return TurnResult(answer=answer, correlation_id=request.correlation_id, header=parse_header(answer),
                              trace=self.harness.finished_trace(request.correlation_id),
                              warnings=["Stopped at the request deadline."], error="deadline")
        except Exception as exc:  # noqa: BLE001 - becomes a controlled message
            log_event("orchestrator", "turn_failed", correlation_id=request.correlation_id, level="ERROR",
                      error_type=type(exc).__name__, message=str(exc)[:300])
            return TurnResult(
                answer=(f"The investigation could not finish ({type(exc).__name__}). Nothing was concluded. "
                        f"Try again, or escalate with correlation ID {request.correlation_id}."),
                correlation_id=request.correlation_id, header=parse_header(""),
                trace=self.harness.finished_trace(request.correlation_id), error=type(exc).__name__)
        finally:
            self._busy.discard(session_id)

        answer, pending, errors = seen["answer"], seen["pending"], seen["errors"]
        trace = self.harness.finished_trace(request.correlation_id)
        if pending:
            self._paused[pending["request_id"]] = request.correlation_id
        warnings = []
        if trace and trace.get("invalid_citations"):
            warnings.append("Unverified evidence IDs (not returned by any tool in this investigation): "
                            + ", ".join(trace["invalid_citations"]))
        if trace and trace.get("termination") not in (None, "NORMAL"):
            warnings.append(f"Stopped by the harness: {trace['termination']}")
        if answer.startswith(REFUSAL_PREFIX):
            warnings.append("The harness stopped this request; the answer is incomplete.")
        if errors and not answer:
            warnings.append("Agent error: " + errors[-1][:200])
        if not answer and pending is None:
            answer = "(No answer was produced. Try again, or escalate with the correlation ID.)"
        header = parse_header(answer)
        if pending is None:
            # Code checks the header against what actually happened (this run, and the run it resumes).
            parent = self.harness.finished_trace(request.parent_correlation_id) \
                if request.parent_correlation_id else None
            answer, header, fixes = answer_guard.check(answer, header, [t for t in (parent, trace) if t])
            if fixes:
                warnings.append("Checked by code: " + "; ".join(fixes))
                log_event("orchestrator", "answer_corrected", correlation_id=request.correlation_id,
                          level="WARNING", fixes=fixes)
        return TurnResult(answer=answer, correlation_id=request.correlation_id, header=header,
                          pending_confirmation=pending, trace=trace, warnings=warnings)


async def specialist_reachable(timeout: float = 2.0) -> bool:
    """Is the Fulfilment Specialist's Agent Card reachable? (shown in the UI; not used for routing)"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(config.FULFILMENT_AGENT_CARD_URL)
        return response.status_code == 200
    except httpx.HTTPError:
        return False
