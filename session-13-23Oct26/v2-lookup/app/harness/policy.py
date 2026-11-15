from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPolicy:
    """Budgets enforced by the runtime harness."""

    max_model_calls: int
    max_tool_calls: int
    max_same_tool_calls: int
    max_failures: int
    max_elapsed_seconds: float

    @classmethod
    def from_environment(cls) -> "ExecutionPolicy":
        """Build the active policy from trusted runtime configuration."""
        return cls(
            max_model_calls=int(os.getenv("MAX_MODEL_CALLS_PER_INVOCATION", "6")),
            max_tool_calls=int(os.getenv("MAX_TOOL_CALLS_PER_INVOCATION", "8")),
            max_same_tool_calls=int(os.getenv("MAX_SAME_TOOL_CALLS", "3")),
            max_failures=int(os.getenv("MAX_FAILURES_PER_INVOCATION", "2")),
            max_elapsed_seconds=float(os.getenv("MAX_INVOCATION_SECONDS", "45")),
        )
