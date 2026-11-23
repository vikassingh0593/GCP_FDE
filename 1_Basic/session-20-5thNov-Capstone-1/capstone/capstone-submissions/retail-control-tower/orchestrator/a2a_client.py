"""Calls the Fulfilment Specialist over A2A, and turns every failure into a clear "unavailable".

Session 19 attached the RemoteA2aAgent as a sub-agent. That hands the whole
conversation to the remote agent (transfer), and when the remote is down the
user sees a raw A2A error. Here the remote agent is wrapped as ONE tool,
check_fulfilment, so:

- the orchestrator keeps control and combines the result with its own evidence;
- the harness counts it like any tool call (allowlist, budgets, trace);
- a timeout or a dead specialist becomes the standard error result, and the
  orchestrator gives a partial answer marked "fulfilment check unavailable",
  never a guessed stock figure (A2A checkpoint);
- the reply is checked against the contract on the Agent Card before use.

Correlation ID: a2a_request_meta_provider copies the request context from this
run's RunConfig into the A2A request metadata. The specialist's harness reads
it from custom_metadata["a2a_metadata"], so both services log the same ID.

This file never imports the specialist's code: only its card URL.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.tools import ToolContext
from google.adk.tools.agent_tool import AgentTool

from common import config, results
from common.harness.context import from_metadata
from common.harness.logs import log_event
from common.inputs import ORDER_ID, clean_id

VERDICTS = {"yes", "no", "unknown", "not_applicable"}
REQUIRED = ("order_id", "verdict", "reason", "evidence_ids", "explanation")
SOURCE = "a2a:fulfilment_specialist"
UNAVAILABLE_HINT = ("Fulfilment check unavailable. Do not state any stock number or a stock-based cause; "
                    "mark fulfilment UNKNOWN and put 'run the fulfilment check again' under check next.")


def forward_trace_context(ctx, a2a_message) -> dict:
    """A2A request metadata = this run's trusted request context (correlation ID, user, session)."""
    request = from_metadata(getattr(ctx.run_config, "custom_metadata", None))
    return request.to_metadata() if request else {}


def build_remote_specialist(card_url: str | None = None, timeout: float | None = None) -> RemoteA2aAgent:
    return RemoteA2aAgent(
        name="fulfilment_specialist",
        description="Remote Fulfilment Specialist (A2A): can the assigned warehouse fulfil an order now.",
        agent_card=card_url or config.FULFILMENT_AGENT_CARD_URL,
        timeout=float(timeout or config.FULFILMENT_TIMEOUT_SECONDS),
        a2a_request_meta_provider=forward_trace_context,
        use_legacy=False,
    )


def parse_reply(text: str, order_id: str) -> dict | None:
    """The specialist's JSON reply, checked against the contract; None if it doesn't hold."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        reply = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            reply = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(reply, dict) or any(k not in reply for k in REQUIRED):
        return None
    if reply["verdict"] not in VERDICTS or reply.get("order_id", "").upper() != order_id:
        return None
    if not isinstance(reply["evidence_ids"], list):
        return None
    return reply


def _snapshot_time(reply: dict) -> datetime | None:
    value = reply.get("inventory_snapshot_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def make_check_fulfilment(card_url: str | None = None, timeout: float | None = None):
    """The check_fulfilment tool, bound to one specialist endpoint (evals point it at a dead one)."""
    remote = build_remote_specialist(card_url, timeout)
    # include_plugins=False: the specialist runs its own harness on its side of the boundary.
    agent_tool = AgentTool(agent=remote, include_plugins=False)
    limit = float(timeout or config.FULFILMENT_TIMEOUT_SECONDS)

    async def check_fulfilment(order_id: str, tool_context: ToolContext) -> dict:
        """Ask the remote Fulfilment Specialist whether the order's ASSIGNED warehouse can fulfil it now.

        Returns verdict (yes / no / unknown / not_applicable), reason, on-hand,
        reserved and available stock with the inventory snapshot time and
        freshness, the orders holding reserved stock, re-route options and
        evidence IDs. Use for orders not yet shipped. If it returns an error,
        fulfilment is UNKNOWN: never guess stock.
        """
        order_id = clean_id(order_id)
        if not ORDER_ID.match(order_id):
            return results.error(SOURCE, "invalid_argument", "order_id must look like ORD-12345")
        request = from_metadata(getattr(tool_context.run_config, "custom_metadata", None))
        correlation_id = request.correlation_id if request else None
        started = time.perf_counter()
        try:
            reply_text = await asyncio.wait_for(
                agent_tool.run_async(args={"request": json.dumps({"task": "fulfilment_check", "order_id": order_id})},
                                     tool_context=tool_context),
                timeout=limit + 2)
        except asyncio.TimeoutError:
            reply_text, outcome = None, "timeout"
        except Exception as exc:  # noqa: BLE001 - any transport failure is "unavailable"
            reply_text, outcome = None, f"unavailable: {type(exc).__name__}"
        else:
            outcome = "ok"
        latency_ms = round((time.perf_counter() - started) * 1000)

        reply = parse_reply(reply_text, order_id) if outcome == "ok" else None
        if reply is None:
            if outcome == "ok":
                outcome = ("unavailable: " + reply_text[:120]) if isinstance(reply_text, str) and \
                    reply_text.startswith(("A2A request failed", "Failed to initialize")) else "bad_reply"
            log_event("orchestrator", "a2a_call", correlation_id=correlation_id, level="WARNING",
                      order_id=order_id, outcome=outcome, latency_ms=latency_ms)
            kind = "timeout" if outcome == "timeout" else "unavailable"
            out = results.error(SOURCE, kind, f"{UNAVAILABLE_HINT} (reason: {outcome.split(':')[0]})")
            out["_trace"] = {"a2a": "fulfilment_specialist", "outcome": outcome, "latency_ms": latency_ms}
            return out

        log_event("orchestrator", "a2a_call", correlation_id=correlation_id, order_id=order_id, outcome="ok",
                  verdict=reply["verdict"], reason=reply["reason"], latency_ms=latency_ms)
        out = results.ok("FUL", order_id, SOURCE, reply, source_time=_snapshot_time(reply),
                         max_age_minutes=config.INVENTORY_MAX_AGE_MINUTES if _snapshot_time(reply) else None)
        out["_trace"] = {"a2a": "fulfilment_specialist", "outcome": "ok", "latency_ms": latency_ms,
                         "verdict": reply["verdict"], "reason": reply["reason"]}
        return out

    return check_fulfilment
