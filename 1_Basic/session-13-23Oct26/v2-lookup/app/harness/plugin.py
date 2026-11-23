from __future__ import annotations

from google.adk.plugins.base_plugin import BasePlugin

from .registry import REGISTRY

class RuntimeTelemetryPlugin(BasePlugin):
    """Record cross-cutting run lifecycle events for the active trace."""

    def __init__(self) -> None:
        super().__init__(name="runtime_telemetry")


    async def before_run_callback(self, *, invocation_context):
        """Observe the start of an ADK run."""
        trace = REGISTRY.current()

        if trace is not None:
            trace.add_event(
                "PLUGIN_BEFORE_RUN",
                invocation_id=getattr(
                    invocation_context,
                    "invocation_id",
                    None,
                ),
            )

        return None


    async def after_run_callback(self, *, invocation_context):
        """Observe completion of an ADK run."""
        trace = REGISTRY.current()

        if trace is not None:
            trace.add_event(
                "PLUGIN_AFTER_RUN",
                invocation_id=getattr(
                    invocation_context,
                    "invocation_id",
                    None,
                ),
            )

        return None