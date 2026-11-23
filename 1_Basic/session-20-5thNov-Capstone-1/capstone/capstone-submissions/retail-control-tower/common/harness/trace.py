"""Execution record for one invocation (session 13 trace.py).

Same event vocabulary as session 13 (REQUEST_ACCEPTED, BEFORE_MODEL,
TOOL_PROPOSED, TOOL_ALLOWED, POLICY_BLOCK, TOOL_COMPLETED, TOOL_FAILURE,
INVOCATION_END), plus what the capstone needs to reproduce a bad answer: the
evidence IDs each tool returned, which of them the answer cited, and the
per-tool details tools attach (retrieval strategy, cache hit, documents; A2A
outcome and latency).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any

from common.harness.context import RequestContext
from common.harness.policy import ExecutionPolicy
from common.masking import mask

RUNNING = "RUNNING"


@dataclass
class TraceEvent:
    kind: str
    detail: dict[str, Any]
    elapsed_seconds: float


@dataclass
class InvocationTrace:
    """Mutable record scoped to one invocation of one service."""

    service: str
    invocation_id: str
    request: RequestContext
    policy: ExecutionPolicy
    started_monotonic: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    tool_calls: int = 0
    failures: int = 0
    termination_reason: str = RUNNING
    # Soft stop: tools are blocked, and the model gets ONE closing call to write the answer from the
    # evidence it has. Hard stop: no more model calls either (model budget used, or out of time).
    tools_blocked: bool = False
    hard_stop: bool = False
    closing_call_used: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    tool_fingerprints: dict[str, int] = field(default_factory=dict)
    tools: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    cited_ids: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)
    events: list[TraceEvent] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_monotonic

    @property
    def stopped(self) -> bool:
        return self.termination_reason != RUNNING

    def add_event(self, kind: str, **detail: Any) -> None:
        self.events.append(TraceEvent(kind=kind, detail=mask(detail), elapsed_seconds=round(self.elapsed_seconds, 3)))

    def add_tokens(self, tokens_in: int | None, tokens_out: int | None) -> None:
        self.tokens_in += tokens_in or 0
        self.tokens_out += tokens_out or 0

    @staticmethod
    def fingerprint(tool_name: str, args: dict[str, Any]) -> str:
        normalized = json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(f"{tool_name}:{normalized}".encode()).hexdigest()[:16]

    def record_tool_proposal(self, tool_name: str, args: dict[str, Any]) -> int:
        """Count a proposed call and return how many times this exact call has been proposed."""
        fp = self.fingerprint(tool_name, args)
        self.tool_fingerprints[fp] = self.tool_fingerprints.get(fp, 0) + 1
        self.add_event("TOOL_PROPOSED", tool=tool_name, args=args, repeat_count=self.tool_fingerprints[fp])
        return self.tool_fingerprints[fp]

    def record_failure(self, tool_name: str, code: str) -> None:
        self.failures += 1
        self.add_event("TOOL_FAILURE", tool=tool_name, code=code)

    def stop(self, reason: str, message: str, *, hard: bool = False) -> None:
        """Block further tools (soft), or tools and model calls (hard).

        First reason wins: later checks don't overwrite why the run stopped. A
        soft stop can still become hard (e.g. the closing call proposes a tool).
        """
        if not self.stopped:
            self.termination_reason = reason
            self.add_event("POLICY_BLOCK", code=reason, message=message, hard=hard)
        elif hard and not self.hard_stop:
            self.add_event("POLICY_BLOCK", code=reason, message=message, hard=True)
        self.tools_blocked = True
        self.hard_stop = self.hard_stop or hard

    def finish(self, reason: str = "NORMAL") -> None:
        if not self.stopped:
            self.termination_reason = reason
        self.add_event("INVOCATION_END", reason=self.termination_reason)

    def to_row(self) -> dict[str, Any]:
        """One masked row per invocation, for output/traces/<service>.jsonl and the web inspector."""
        return {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "service": self.service,
            "correlation_id": self.request.correlation_id,
            "parent_correlation_id": self.request.parent_correlation_id,
            "invocation_id": self.invocation_id,
            "session_id": self.request.session_id,
            "user": self.request.user,
            "environment": self.request.environment,
            "termination": self.termination_reason,
            "latency_s": round(self.elapsed_seconds, 2),
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "failures": self.failures,
            "hard_stop": self.hard_stop,
            "closing_call_used": self.closing_call_used,
            "tokens": {"in": self.tokens_in, "out": self.tokens_out},
            "budgets": {"model_calls": self.policy.max_model_calls, "tool_calls": self.policy.max_tool_calls,
                        "failures": self.policy.max_failures, "seconds": self.policy.max_elapsed_seconds},
            "tools": mask(self.tools),
            "evidence_ids": self.evidence_ids,
            "cited_ids": self.cited_ids,
            "invalid_citations": self.invalid_citations,
            "details": self.details,
            "events": [{"kind": e.kind, "t": e.elapsed_seconds, **e.detail} for e in self.events],
        }
