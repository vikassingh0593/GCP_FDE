"""The harness: one ADK plugin on the Runner of BOTH services (orchestrator and specialist).

Session 13 put the budget checks in agent callbacks and a separate telemetry
plugin, and it only recorded problems. Here everything sits in one plugin on
the Runner (App(plugins=[...])), so every agent the Runner drives is covered,
and it blocks:

- Fails closed: a run without a correlation ID or a user is refused before any
  model or tool call.
- Budgets block, not just record: model calls, tool calls, the same tool with
  the same arguments, failures and wall-clock time.
- Two kinds of stop, so a stopped run still ends with a usable answer:
    soft  (tool budget, repeated call, failures, model budget nearly used):
          tools are blocked and the model gets ONE closing call to write the
          answer from the evidence it already has;
    hard  (model budget used, out of time, or the closing call asked for more
          tools): no more model calls; the answer is the stop message.
  The last model call is always kept for the answer: tools stop one model
  call before the model budget runs out.
- Tool allowlist: a tool not registered for this service never runs.
- A raw tool exception never reaches the model: it becomes the standard
  error result (common.results).
- Arguments and results are masked before they are logged.
- Citations are checked: every evidence ID in the final answer must have been
  returned by a tool in this invocation. Unknown IDs are recorded, and the
  runtime shows them as unverified. "Returned" means in this session: the IDs
  every tool returned are kept in session state (evidence_ids_seen), because a
  follow-up turn, or the answer after an escalation confirmation, rightly cites
  evidence gathered in an earlier invocation. A structured reply (output_schema, sent
  through set_model_response) is checked the same way on its evidence_ids
  field, so the specialist can't pass an invented ID across A2A unnoticed.
- One trace row per invocation in output/traces/<service>.jsonl, with the
  termination reason, the tools, the evidence and the tool details, so a bad
  answer can be reproduced.

Tools can attach a "_trace" dict to their result (e.g. retrieval strategy and
cache hit). The plugin moves it into the trace and removes it from the result,
so it never reaches the model.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from google.adk.plugins.base_plugin import BasePlugin
from google.genai import types

from common import results
from common.harness.context import from_metadata
from common.inputs import EVIDENCE_ID
from common.harness.logs import log_event, write_trace
from common.harness.policy import ExecutionPolicy
from common.harness.trace import InvocationTrace

REFUSAL_PREFIX = "HARNESS_STOP"
SEEN_KEY = "evidence_ids_seen"      # session state: evidence IDs returned by tools in this session
MAX_SEEN = 300

def cited_evidence_ids(text: str) -> list[str]:
    return list(dict.fromkeys(EVIDENCE_ID.findall(text or "")))


def _text_of(content: types.Content | None) -> str:
    if content is None or not content.parts:
        return ""
    return "".join(p.text for p in content.parts if getattr(p, "text", None) and not getattr(p, "thought", False))


def _harness_block(result: dict) -> dict:
    """Mark a result the harness itself returned (refused or blocked call).

    ADK still runs after_tool_callback on it; the mark stops that callback from
    recording the call a second time and counting it as a tool failure.
    """
    return {**result, "_harness": "blocked"}


def _has_function_call(content: types.Content | None) -> bool:
    return bool(content and content.parts and any(getattr(p, "function_call", None) for p in content.parts))


class HarnessPlugin(BasePlugin):
    """Runtime controls for one service. `allowed_tools` is the service's tool allowlist."""

    def __init__(self, service: str, allowed_tools: set[str], policy: ExecutionPolicy | None = None,
                 keep_finished: int = 200, track_session_evidence: bool = True, build: dict | None = None):
        super().__init__(name=f"harness_{service}")
        self.service = service
        self.allowed_tools = set(allowed_tools)
        self.policy = policy or ExecutionPolicy.from_config()
        self.active: dict[str, InvocationTrace] = {}
        self.finished: "OrderedDict[str, dict]" = OrderedDict()   # correlation ID -> last trace row
        self._keep = keep_finished
        # Off for the specialist: its A2A sessions last one request, and ADK warns about (and drops)
        # state changes sent back to the caller over A2A.
        self.track_session_evidence = track_session_evidence
        # What produced the answer (app version, model, temperature, instruction hash...): on every trace row.
        self.build = dict(build or {})

    # -------------------------------------------------------------- helpers

    def trace_for(self, invocation_id: str | None) -> InvocationTrace | None:
        return self.active.get(invocation_id or "")

    def finished_trace(self, correlation_id: str) -> dict | None:
        """The trace row of a finished invocation, for the web inspector and the evals."""
        return self.finished.get(correlation_id)

    def _check_citations(self, trace: InvocationTrace, cited: list[str], earlier: list[str] | None = None) -> None:
        if not cited:
            return
        known = set(trace.evidence_ids) | set(earlier or [])
        trace.cited_ids = list(dict.fromkeys(cited))
        trace.invalid_citations = [c for c in trace.cited_ids if c not in known]
        if trace.invalid_citations:
            trace.add_event("CITATION_CHECK_FAILED", unknown=trace.invalid_citations)
            log_event(self.service, "citation_check_failed", correlation_id=trace.request.correlation_id,
                      level="WARNING", unknown=trace.invalid_citations)

    def _check_time(self, trace: InvocationTrace) -> None:
        if trace.elapsed_seconds > trace.policy.max_elapsed_seconds:
            trace.stop("INVOCATION_TIME_BUDGET_EXCEEDED", "The invocation exceeded its wall-clock budget.", hard=True)

    def _stop_message(self, trace: InvocationTrace) -> str:
        return (f"{REFUSAL_PREFIX} ({trace.termination_reason}): the investigation stopped before finishing. "
                "Only the evidence gathered so far can be reported; everything else is UNKNOWN and should be "
                f"escalated to an analyst. Correlation ID {trace.request.correlation_id}.")

    # -------------------------------------------------------------- run

    async def before_run_callback(self, *, invocation_context) -> Optional[types.Content]:
        run_config = getattr(invocation_context, "run_config", None)
        request = from_metadata(getattr(run_config, "custom_metadata", None))
        if request is None:
            log_event(self.service, "refused_no_context", correlation_id=None, level="WARNING",
                      invocation_id=invocation_context.invocation_id)
            return types.Content(role="model", parts=[types.Part(text=(
                f"{REFUSAL_PREFIX}: request refused because its trace context (user and correlation ID) "
                "is missing. Nothing was looked up."))])

        trace = InvocationTrace(service=self.service, invocation_id=invocation_context.invocation_id,
                                request=request, policy=self.policy)
        trace.add_event("REQUEST_ACCEPTED", correlation_id=request.correlation_id, user=request.user,
                        parent_correlation_id=request.parent_correlation_id)
        self.active[invocation_context.invocation_id] = trace
        log_event(self.service, "run_start", correlation_id=request.correlation_id, user=request.user,
                  session_id=request.session_id, parent_correlation_id=request.parent_correlation_id,
                  invocation_id=invocation_context.invocation_id)
        return None

    async def after_run_callback(self, *, invocation_context) -> None:
        trace = self.active.pop(invocation_context.invocation_id, None)
        if trace is None:
            return
        trace.finish("NORMAL")
        self._close(trace)

    async def on_run_error_callback(self, *, invocation_context, error: Exception) -> None:
        trace = self.active.pop(invocation_context.invocation_id, None)
        if trace is None:
            return
        trace.add_event("UNHANDLED_RUNTIME_ERROR", error_type=type(error).__name__, message=str(error)[:300])
        trace.finish("UNHANDLED_RUNTIME_ERROR")
        self._close(trace)

    def abandon(self, correlation_id: str, reason: str) -> None:
        """Close the trace of a run the caller gave up on (request deadline): it would never finish otherwise."""
        for invocation_id, trace in list(self.active.items()):
            if trace.request.correlation_id == correlation_id:
                self.active.pop(invocation_id, None)
                trace.stop(reason, "The caller stopped waiting for this run.", hard=True)
                trace.finish(reason)
                self._close(trace)

    def _close(self, trace: InvocationTrace) -> None:
        row = trace.to_row()
        row["build"] = self.build
        write_trace(self.service, row)
        self.finished[trace.request.correlation_id] = row
        while len(self.finished) > self._keep:
            self.finished.popitem(last=False)
        log_event(self.service, "run_end", correlation_id=trace.request.correlation_id,
                  level="INFO" if row["termination"] == "NORMAL" else "WARNING",
                  termination=row["termination"], latency_s=row["latency_s"], model_calls=trace.model_calls,
                  tool_calls=trace.tool_calls, failures=trace.failures, tokens_in=trace.tokens_in,
                  tokens_out=trace.tokens_out, invalid_citations=trace.invalid_citations)

    # -------------------------------------------------------------- model

    async def before_model_callback(self, *, callback_context, llm_request):
        from google.adk.models.llm_response import LlmResponse

        trace = self.trace_for(callback_context.invocation_id)
        if trace is None:   # a model call outside a run we accepted: fail closed
            return LlmResponse(content=types.Content(role="model", parts=[types.Part(
                text=f"{REFUSAL_PREFIX}: no trace context for this model call.")]))

        if trace.model_calls >= trace.policy.max_model_calls:
            trace.stop("MODEL_BUDGET_EXCEEDED", "The invocation used its model-call budget.", hard=True)
        self._check_time(trace)
        if trace.tools_blocked and not trace.hard_stop:
            if trace.closing_call_used:          # the closing call asked for tools instead of answering
                trace.stop(trace.termination_reason, "The closing call did not write an answer.", hard=True)
            else:
                trace.closing_call_used = True
                trace.add_event("CLOSING_CALL", reason=trace.termination_reason)
        if trace.hard_stop:
            return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=self._stop_message(trace))]))

        trace.model_calls += 1
        trace.add_event("BEFORE_MODEL", model_call=trace.model_calls)
        return None

    async def after_model_callback(self, *, callback_context, llm_response):
        trace = self.trace_for(callback_context.invocation_id)
        if trace is None:
            return None
        usage = getattr(llm_response, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", None)
        tokens_out = getattr(usage, "candidates_token_count", None)
        trace.add_tokens(tokens_in, tokens_out)
        trace.add_event("AFTER_MODEL", tokens_in=tokens_in, tokens_out=tokens_out)

        content = getattr(llm_response, "content", None)
        if getattr(llm_response, "partial", False) or _has_function_call(content):
            return None
        earlier = list(callback_context.state.get(SEEN_KEY) or [])
        self._check_citations(trace, cited_evidence_ids(_text_of(content)), earlier)
        return None

    async def on_model_error_callback(self, *, callback_context, llm_request, error):
        trace = self.trace_for(callback_context.invocation_id)
        log_event(self.service, "model_error", correlation_id=trace.request.correlation_id if trace else None,
                  level="ERROR", error_type=type(error).__name__, message=str(error)[:300])
        return None   # the error propagates; the runtime turns it into a controlled message

    # -------------------------------------------------------------- tools

    async def before_tool_callback(self, *, tool, tool_args, tool_context):
        name = getattr(tool, "name", type(tool).__name__)
        trace = self.trace_for(tool_context.invocation_id)
        if trace is None:
            return results.error(name, "policy", "no trace context for this tool call; refused")

        if name not in self.allowed_tools:
            trace.add_event("TOOL_NOT_ALLOWED", tool=name)
            trace.tools.append({"tool": name, "args": tool_args, "outcome": "refused:not_allowlisted"})
            log_event(self.service, "tool_refused", correlation_id=trace.request.correlation_id,
                      level="WARNING", tool=name, reason="not_allowlisted")
            return _harness_block(results.error(name, "policy", f"tool {name} is not allowed for this service"))

        repeat_count = trace.record_tool_proposal(name, tool_args)
        self._check_time(trace)
        if trace.tool_calls >= trace.policy.max_tool_calls:
            trace.stop("TOOL_BUDGET_EXCEEDED", "The invocation used its tool-call budget.")
        if repeat_count > trace.policy.max_same_tool_calls:
            trace.stop("REPEATED_CALL_PATTERN", "The same tool and arguments were proposed too many times.")
        if trace.failures > trace.policy.max_failures:
            trace.stop("FAILURE_BUDGET_EXCEEDED", "Too many tool failures in this invocation.")
        if trace.model_calls >= trace.policy.max_model_calls - 1:
            # The next model call is the last one allowed: keep it for the answer.
            trace.stop("MODEL_BUDGET_EXCEEDED", "Model-call budget nearly used: tools stopped so the last "
                                                "model call can write the answer.")
        if trace.tools_blocked:
            trace.tools.append({"tool": name, "args": tool_args, "outcome": f"blocked:{trace.termination_reason}"})
            return _harness_block(results.error(
                name, "budget", f"blocked by the harness ({trace.termination_reason}). Make no more tool calls: "
                                "write the answer now from the evidence already gathered, and mark everything "
                                "else UNKNOWN."))

        trace.tool_calls += 1
        trace.add_event("TOOL_ALLOWED", tool=name, function_call_id=getattr(tool_context, "function_call_id", None))
        log_event(self.service, "tool_call", correlation_id=trace.request.correlation_id, tool=name, args=tool_args)
        return None

    async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
        name = getattr(tool, "name", type(tool).__name__)
        trace = self.trace_for(tool_context.invocation_id)
        if trace is None or not isinstance(result, dict):
            return None
        if result.get("_harness") == "blocked":          # already recorded in before_tool
            return {k: v for k, v in result.items() if k != "_harness"}
        if name == "set_model_response":                 # the structured reply: check its evidence IDs
            ids = tool_args.get("evidence_ids") if isinstance(tool_args, dict) else None
            self._check_citations(trace, [i for i in ids or [] if isinstance(i, str)])

        cleaned = None
        if "_trace" in result:
            cleaned = {k: v for k, v in result.items() if k != "_trace"}
            if isinstance(result["_trace"], dict):
                trace.details.append({"tool": name, **result["_trace"]})
            result = cleaned

        # No status but an "error" key: ADK's own reply, e.g. a confirmation not given or declined.
        status = result.get("status") or ("not_run" if "error" in result else "other")
        new_ids = results.collect_evidence_ids(result)
        trace.evidence_ids.extend(i for i in new_ids if i not in trace.evidence_ids)
        if new_ids and self.track_session_evidence:
            seen = list(tool_context.state.get(SEEN_KEY) or [])
            seen += [i for i in new_ids if i not in seen]
            tool_context.state[SEEN_KEY] = seen[-MAX_SEEN:]
        trace.tools.append({"tool": name, "args": tool_args, "outcome": status,
                            "evidence_ids": new_ids, "freshness": result.get("freshness")})
        trace.add_event("TOOL_COMPLETED", tool=name, status=status, code=result.get("error_type"))
        if status == "error":
            trace.record_failure(name, result.get("error_type") or "UNKNOWN_TOOL_FAILURE")
            if trace.failures > trace.policy.max_failures:
                trace.stop("FAILURE_BUDGET_EXCEEDED", "Too many tool failures in this invocation.")
        log_event(self.service, "tool_result", correlation_id=trace.request.correlation_id, tool=name,
                  status=status, evidence_ids=new_ids, freshness=result.get("freshness"))
        return cleaned

    async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
        """A raw exception becomes the standard error result, so the model sees a fact, not a traceback."""
        name = getattr(tool, "name", type(tool).__name__)
        trace = self.trace_for(tool_context.invocation_id)
        kind = "timeout" if "timeout" in type(error).__name__.lower() else "unavailable"
        if trace is not None:
            trace.tools.append({"tool": name, "args": tool_args, "outcome": "exception"})
            trace.record_failure(name, kind)
        log_event(self.service, "tool_exception", correlation_id=trace.request.correlation_id if trace else None,
                  level="ERROR", tool=name, error_type=type(error).__name__, message=str(error)[:300])
        return results.error(name, kind, f"{name} failed ({type(error).__name__}); treat its facts as UNKNOWN")
