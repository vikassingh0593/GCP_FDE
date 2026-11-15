from __future__ import annotations

from .trace import InvocationTrace


def render_report(trace: InvocationTrace) -> str:
    """Render a human-readable report for the active trace."""

    p = trace.policy

    lines = [
        "",
        "=" * 66,
        "ENTERPRISE ADK INVOCATION REPORT",
        "=" * 66,
        f"Correlation ID : {trace.request.correlation_id}",
        f"Tenant         : {trace.request.tenant_id}",
        f"User           : {trace.request.user_id}",
        f"Environment    : {trace.request.environment}",
        f"Termination    : {trace.termination_reason}",
        f"Elapsed        : {trace.elapsed_seconds:.2f}s / {p.max_elapsed_seconds:.0f}s",
        "",
        "BUDGET / USAGE",
        f"Model calls    : {trace.model_calls} / {p.max_model_calls}",
        f"Tool calls     : {trace.tool_calls} / {p.max_tool_calls}",
        f"Failures       : {trace.failures} / {p.max_failures}",
        "",
        "TRACE",
    ]


    for index, event in enumerate(trace.events, start=1):
        lines.append(
            f"{index:02d}. +{event.elapsed_seconds:>6.3f}s "
            f"{event.kind:<22} {event.detail}"
        )

    lines.append("=" * 66)
    return "\n".join(lines)