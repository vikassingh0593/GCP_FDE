from __future__ import annotations

from typing import Any

from google.adk.tools import BaseTool, ToolContext

from .harness.registry import REGISTRY

def _policy_block(code: str, message: str) -> dict[str, Any]:
    """Create a controlled harness result that prevents tool execution."""
    trace = REGISTRY.current()

    if trace is not None:
        trace.termination_reason = code
        trace.add_event("POLICY_BLOCK", code=code, message=message)

    return {
        "status": "error",
        "code": code,
        "message": message,
        "retryable": False,
    }



def before_model_callback(callback_context, llm_request):
    """Count model boundaries and enforce model/time budgets."""
    trace = REGISTRY.current()

    if trace is None:
        return None

    trace.model_calls += 1
    trace.add_event(
        "BEFORE_MODEL",
        model_call=trace.model_calls,
    )

    if trace.elapsed_seconds > trace.policy.max_elapsed_seconds:
        trace.termination_reason = "INVOCATION_TIME_BUDGET_EXCEEDED"

    if trace.model_calls > trace.policy.max_model_calls:
        trace.termination_reason = "MODEL_BUDGET_EXCEEDED"

    # Day 1 observes model budget violations in the trace. Tool execution is
    # actively blocked below; full workflow termination strategy comes on Day 2.
    return None



def after_model_callback(callback_context, llm_response):
    """Record completion of a model boundary."""
    trace = REGISTRY.current()

    if trace is not None:
        trace.add_event("AFTER_MODEL")

    return None




def before_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
) -> dict[str, Any] | None:
    """Enforce time, total-call and repeated-call budgets before execution."""
    trace = REGISTRY.current()

    if trace is None:
        return None

    if trace.elapsed_seconds > trace.policy.max_elapsed_seconds:
        return _policy_block(
            "INVOCATION_TIME_BUDGET_EXCEEDED",
            "The invocation exceeded its wall-clock execution budget.",
        )

    repeat_count = trace.record_tool_proposal(
        tool.name,
        args,
    )

    if trace.tool_calls > trace.policy.max_tool_calls:
        return _policy_block(
            "TOOL_BUDGET_EXCEEDED",
            "The invocation exceeded its total tool-call budget.",
        )

    if repeat_count > trace.policy.max_same_tool_calls:
        return _policy_block(
            "REPEATED_CALL_PATTERN",
            "The same tool and arguments were proposed too many times.",
        )

    trace.add_event(
        "TOOL_ALLOWED",
        tool=tool.name,
        function_call_id=getattr(
            tool_context,
            "function_call_id",
            None,
        ),
    )
    return None



def after_tool_callback(
    tool: BaseTool,
    args: dict[str, Any],
    tool_context: ToolContext,
    tool_response: dict[str, Any],
) -> dict[str, Any] | None:
    """Record tool completion and enforce the failure budget."""
    trace = REGISTRY.current()

    if trace is None:
        return None

    status = tool_response.get("status")
    code = tool_response.get("code")

    trace.add_event(
        "TOOL_COMPLETED",
        tool=tool.name,
        status=status,
        code=code,
    )

    if status == "error":
        trace.record_failure(code or "UNKNOWN_TOOL_FAILURE")

        if trace.failures > trace.policy.max_failures:
            trace.termination_reason = "FAILURE_BUDGET_EXCEEDED"

    return None
