
from __future__ import annotations

from contextvars import ContextVar

from .trace import InvocationTrace


_CURRENT_TRACE: ContextVar[InvocationTrace | None] = ContextVar(
    "current_invocation_trace",
    default=None,
)


class InvocationRegistry:
    """Access the trace bound to the current async execution context."""

    def bind(self, trace: InvocationTrace):
        """Bind a trace and return the ContextVar reset token."""
        return _CURRENT_TRACE.set(trace)

    def reset(self, token) -> None:
        """Restore the previous trace binding."""
        _CURRENT_TRACE.reset(token)

    def current(self) -> InvocationTrace | None:
        """Return the active trace, if one is bound."""
        return _CURRENT_TRACE.get()



REGISTRY = InvocationRegistry()
