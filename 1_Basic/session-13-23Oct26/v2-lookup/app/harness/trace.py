from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .context import RequestContext
from .policy import ExecutionPolicy

@dataclass
class TraceEvent:
    """One normalized runtime event."""

    kind: str
    detail: dict[str, Any]
    elapsed_seconds: float


@dataclass
class InvocationTrace:
    """Mutable execution record scoped to one invocation."""

    request: RequestContext
    policy: ExecutionPolicy
    started_monotonic: float = field(default_factory=time.monotonic)
    model_calls: int = 0
    tool_calls: int = 0
    failures: int = 0
    termination_reason: str = "RUNNING"
    tool_fingerprints: dict[str, int] = field(default_factory=dict)
    events: list[TraceEvent] = field(default_factory=list)

    @property
    def elapsed_seconds(self) -> float:
        """Return wall-clock elapsed time for this invocation."""
        return time.monotonic() - self.started_monotonic

    def add_event(self, kind: str, **detail: Any) -> None:
        """Append one normalized trace event."""
        self.events.append(
            TraceEvent(
                kind=kind,
                detail=detail,
                elapsed_seconds=round(self.elapsed_seconds, 3),
            )
        )

    def fingerprint(self, tool_name: str, args: dict[str, Any]) -> str:
        """Create a stable fingerprint for repeated-call detection."""
        normalized = json.dumps(
            args,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        return f"{tool_name}:{normalized}"

    def record_tool_proposal(
        self,
        tool_name: str,
        args: dict[str, Any],
    ) -> int:
        """Record a proposed tool call and return its repetition count."""
        self.tool_calls += 1
        fp = self.fingerprint(tool_name, args)
        self.tool_fingerprints[fp] = self.tool_fingerprints.get(fp, 0) + 1
        repeat_count = self.tool_fingerprints[fp]

        self.add_event(
            "TOOL_PROPOSED",
            tool=tool_name,
            args=args,
            repeat_count=repeat_count,
        )
        return repeat_count

    def record_failure(self, code: str) -> None:
        """Increment failure metrics and add a trace event."""
        self.failures += 1
        self.add_event("TOOL_FAILURE", code=code)

    def finish(self, reason: str = "NORMAL") -> None:
        """Mark the invocation as terminated."""
        self.termination_reason = reason
        self.add_event("INVOCATION_END", reason=reason)
