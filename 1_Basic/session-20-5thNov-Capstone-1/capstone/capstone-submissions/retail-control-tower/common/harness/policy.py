"""Budgets enforced by the harness (session 13 policy.py, Gate 11).

Values come from lab.env through common.config, so both services read the same
numbers and a typo fails at startup, not mid-investigation.
"""

from __future__ import annotations

from dataclasses import dataclass

from common import config


@dataclass(frozen=True)
class ExecutionPolicy:
    """Per-invocation limits. Over a limit, the harness blocks the call (session 13 only recorded it)."""

    max_model_calls: int
    max_tool_calls: int
    max_same_tool_calls: int
    max_failures: int
    max_elapsed_seconds: float

    @classmethod
    def from_config(cls) -> "ExecutionPolicy":
        return cls(
            max_model_calls=config.MAX_MODEL_CALLS_PER_INVOCATION,
            max_tool_calls=config.MAX_TOOL_CALLS_PER_INVOCATION,
            max_same_tool_calls=config.MAX_SAME_TOOL_CALLS,
            max_failures=config.MAX_FAILURES_PER_INVOCATION,
            max_elapsed_seconds=float(config.MAX_INVOCATION_SECONDS),
        )
