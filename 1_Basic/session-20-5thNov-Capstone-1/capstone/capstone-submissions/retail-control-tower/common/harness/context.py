"""Trusted request metadata, created by the caller, never by the model (session 13 context.py).

The web runtime creates one RequestContext per analyst message and passes it
to the Runner in RunConfig.custom_metadata. The orchestrator forwards it to the
specialist as A2A request metadata; ADK on the specialist side exposes that as
custom_metadata["a2a_metadata"]. from_metadata() reads both shapes, so the
same harness works in both services and one correlation ID follows the request
from the browser to the specialist's inventory read.

Change from session 13: the context travels with the request (RunConfig and
A2A metadata) instead of a process-local ContextVar, because the specialist
runs in another process.

parent_correlation_id links a run that resumes another one: the analyst's
answer to an escalation confirmation is a new request (new correlation ID)
whose parent is the request that asked for the confirmation.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from common import config

A2A_METADATA_KEY = "a2a_metadata"   # where ADK puts incoming A2A request metadata


def new_correlation_id() -> str:
    return f"corr-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class RequestContext:
    """Trusted metadata attached to one request."""

    correlation_id: str
    user: str                       # pseudonymous analyst ID, never a name or email
    session_id: str | None = None
    parent_correlation_id: str | None = None
    environment: str = config.LAB_ENVIRONMENT
    received_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_metadata(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def create(cls, user: str, session_id: str | None = None,
               parent_correlation_id: str | None = None) -> "RequestContext":
        return cls(correlation_id=new_correlation_id(), user=user, session_id=session_id,
                   parent_correlation_id=parent_correlation_id)


def from_metadata(metadata: Any) -> RequestContext | None:
    """The request context from RunConfig.custom_metadata, or None if it is missing or incomplete."""
    if not metadata:
        return None
    metadata = dict(metadata)
    if isinstance(metadata.get(A2A_METADATA_KEY), dict) and not metadata.get("correlation_id"):
        metadata = dict(metadata[A2A_METADATA_KEY])
    correlation_id = str(metadata.get("correlation_id") or "").strip()
    user = str(metadata.get("user") or "").strip()
    if not correlation_id or not user:
        return None
    return RequestContext(
        correlation_id=correlation_id,
        user=user,
        session_id=metadata.get("session_id"),
        parent_correlation_id=metadata.get("parent_correlation_id"),
        environment=str(metadata.get("environment") or config.LAB_ENVIRONMENT),
        received_at=str(metadata.get("received_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
