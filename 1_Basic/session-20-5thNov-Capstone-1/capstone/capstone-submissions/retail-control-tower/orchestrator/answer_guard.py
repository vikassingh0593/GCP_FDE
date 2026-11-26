"""Code checks the answer's header before the analyst sees it.

Why: the header is what the analyst acts on, and without this nothing but the
prompt stood between the model and a cause it had no proof for.

The model writes OUTCOME / CAUSE / FULFILABLE. Those three lines are what an
analyst acts on, so a prompt rule is not enough: this guard compares them with
what actually happened in the invocation (the harness trace: which tools ran,
how they ended, how fresh the data was, and the facts tools attached for this
purpose) and corrects any claim the evidence doesn't support.

Rules (a correction always moves toward the safer value):
- header missing or a value outside the allowed list -> partial / none / unknown;
- the run was stopped by the harness, or the fulfilment check failed -> partial,
  and FULFILABLE unknown;
- FULFILABLE yes / no / not_now / no_under_current_rule needs a successful,
  fresh fulfilment check whose verdict agrees;
- CAUSE needs its proof in this run: inventory_shortage and allocation_reserved
  the matching fulfilment reason, recent_change a consistent_with_change
  before/after result, carrier_weather_hold a WX-HOLD event, warehouse_disruption
  an open warehouse event, payment_hold a payment hold on the order;
- check_next means the evidence does not confirm a cause, so CAUSE is none
  (live test: "CAUSE carrier_delay" over a text that said the cause was unknown);
- no_problem needs the order looked up and not overdue.

A correction rewrites the header line and adds a "CHECKED BY CODE:" line saying
what changed and why, so the analyst sees it.

Where it runs: make_after_model_check() is the orchestrator's after_model_callback,
so the corrected text is what ADK saves as the event. A reopened session shows
the corrected answer, and the model's next turn reads it in its history. (Run
after the fact, in the runtime, the analyst saw the correction once, while the
session kept the model's original text.) The runtime still calls check() itself
when no model call produced the answer, e.g. a harness stop message. Follow-up answers (OUTCOME
answer) are only checked for the header and FULFILABLE: their cause may rest
on an earlier turn's evidence. Not when the turn looked the order up again:
then the fresh evidence is in this run, and the cause needs its proof here.
"""

from __future__ import annotations

import re

OUTCOMES = {"cause_named", "check_next", "escalate", "not_found", "no_problem", "partial", "clarify", "answer",
            "retrieval_answer"}
CAUSES = {"inventory_shortage", "allocation_reserved", "carrier_weather_hold", "carrier_delay", "payment_hold",
          "warehouse_disruption", "recent_change", "none"}
FULFILABLE = {"yes", "no", "not_now", "no_under_current_rule", "unknown", "not_applicable"}
STOCK_CLAIMS = {"yes", "no", "not_now", "no_under_current_rule"}
NO_CHECKS = {"clarify", "not_found", "retrieval_answer"}
LINE = {k: re.compile(rf"^\s*{k}\s*:.*$", re.M | re.I) for k in ("OUTCOME", "CAUSE", "FULFILABLE")}


def _facts(traces: list[dict]) -> dict:
    calls = [t for tr in traces for t in tr.get("tools", [])]
    details = [d for tr in traces for d in tr.get("details", [])]

    def last(tool: str) -> dict:
        return next((d for d in reversed(details) if d.get("tool") == tool), {})

    fulfil_calls = [c for c in calls if c.get("tool") == "check_fulfilment"]
    a2a = next((d for d in reversed(details) if d.get("a2a") and d.get("outcome") == "ok"), {})
    fresh_ok = any(c.get("outcome") == "ok" and c.get("freshness") == "fresh" for c in fulfil_calls)
    return {
        "stopped": any(tr.get("termination") not in (None, "NORMAL") for tr in traces),
        "fulfil_tried": bool(fulfil_calls),
        "fulfil_ok": any(c.get("outcome") == "ok" for c in fulfil_calls),
        "verdict": a2a.get("verdict") if fresh_ok else None,
        "reason": a2a.get("reason") if fresh_ok else None,
        "order": last("get_order"),
        "patterns": [d.get("pattern") for d in details if d.get("tool") == "compare_before_after_change"],
        "carrier_code": last("get_carrier_events").get("latest_exception_code"),
        "open_events": last("get_warehouse_events").get("open_events") or [],
    }


def _cause_supported(cause: str, f: dict) -> bool:
    return {
        "inventory_shortage": f["verdict"] == "no" and f["reason"] == "true_shortage",
        "allocation_reserved": f["verdict"] == "no" and f["reason"] == "reserved_stock",
        "recent_change": "consistent_with_change" in f["patterns"],
        "carrier_weather_hold": f["carrier_code"] == "WX-HOLD",
        "carrier_delay": bool(f["carrier_code"]) or bool(f["order"].get("shipped")),
        "warehouse_disruption": bool(f["open_events"]),
        "payment_hold": bool(f["order"].get("payment_hold")),
    }.get(cause, True)


def check(answer: str, header: dict, traces: list[dict]) -> tuple[str, dict, list[str]]:
    """(answer with any corrected header, corrected header, what was corrected and why)."""
    h = dict(header)
    fixes: list[str] = []

    def fix(field: str, value: str, why: str) -> None:
        if h.get(field) != value:
            fixes.append(f"{field.upper()} {h.get(field) or 'missing'} -> {value}: {why}")
            h[field] = value

    if h.get("outcome") not in OUTCOMES:
        fix("outcome", "partial", "no valid OUTCOME line")
    if h.get("cause") not in CAUSES:
        fix("cause", "none", "no valid CAUSE line")
    if h.get("fulfilable") not in FULFILABLE:
        fix("fulfilable", "unknown", "no valid FULFILABLE line")

    f = _facts(traces)
    if h["outcome"] not in NO_CHECKS:
        if f["stopped"] and h["outcome"] in ("cause_named", "no_problem"):
            fix("outcome", "partial", "the harness stopped this investigation before it finished")
        if f["fulfil_tried"] and not f["fulfil_ok"]:
            if h["outcome"] in ("cause_named", "no_problem", "check_next"):
                fix("outcome", "partial", "the fulfilment check failed")
            fix("fulfilable", "unknown", "the fulfilment check failed, so stock is not confirmed")

        if h["fulfilable"] in STOCK_CLAIMS:
            v = f["verdict"]
            if v is None:
                fix("fulfilable", "unknown", "no successful, fresh fulfilment check in this investigation")
            elif v == "no" and h["fulfilable"] != "no":
                fix("fulfilable", "no", "the fulfilment check says the stock doesn't cover the order")
            elif v == "yes" and h["fulfilable"] == "no":
                fix("fulfilable", "yes", "the fulfilment check says the stock covers the order")
            elif v in ("unknown", "not_applicable"):
                fix("fulfilable", v, f"the fulfilment check verdict is {v}")

        follow_up_from_memory = h["outcome"] == "answer" and not f["order"]
        if not follow_up_from_memory and h["cause"] != "none" and not _cause_supported(h["cause"], f):
            fix("cause", "none", f"no evidence in this investigation proves {header.get('cause')}")
            if h["outcome"] == "cause_named":
                fix("outcome", "check_next", "the named cause was not proven")
        if h["outcome"] == "check_next" and h["cause"] != "none":
            fix("cause", "none", "check_next means the evidence does not confirm a cause")

        if h["outcome"] == "no_problem" and (not f["order"] or f["order"].get("overdue")):
            fix("outcome", "check_next", "the order was not looked up, or it is overdue")

    if not fixes:
        return answer, h, []
    text = answer or ""
    for field, value in h.items():
        line = f"{field.upper()}: {value}"
        text = LINE[field.upper()].sub(line, text, count=1) if LINE[field.upper()].search(text) else text
    missing = [f"{k.upper()}: {v}" for k, v in h.items() if not LINE[k.upper()].search(text)]
    if missing:
        text = "\n".join(missing) + "\n" + text
    note = "CHECKED BY CODE: " + "; ".join(fixes)
    fulfil_line = LINE["FULFILABLE"].search(text)
    text = text[:fulfil_line.end()] + "\n" + note + text[fulfil_line.end():] if fulfil_line else note + "\n" + text
    return text, h, fixes


CHECKED_EVENT = "ANSWER_CHECKED"


def make_after_model_check(harness):
    """after_model_callback for the orchestrator: check the final answer against this run's trace."""
    from google.genai import types

    def after_model(callback_context, llm_response):
        content = getattr(llm_response, "content", None)
        parts = (content.parts if content else None) or []
        if getattr(llm_response, "partial", False) or any(getattr(p, "function_call", None) for p in parts):
            return None                                 # a tool call or a streamed piece, not the answer
        text = "".join(p.text or "" for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
        trace = harness.trace_for(callback_context.invocation_id)
        if not text.strip() or trace is None:
            return None
        row = trace.to_row()
        if not trace.stopped:
            row["termination"] = "NORMAL"               # still running; only a real stop counts as stopped
        parent = harness.finished_trace(trace.request.parent_correlation_id) \
            if trace.request.parent_correlation_id else None
        checked, _, fixes = check(text.strip(), parse_header(text), [t for t in (parent, row) if t])
        trace.add_event(CHECKED_EVENT, fixes=fixes)
        if not fixes:
            return None
        kept = [p for p in parts if getattr(p, "thought", False)]
        llm_response.content = types.Content(role=content.role or "model", parts=kept + [types.Part(text=checked)])
        return llm_response

    return after_model


HEADER = re.compile(r"^\s*(OUTCOME|CAUSE|FULFILABLE)\s*:\s*([A-Za-z_]+)", re.M)


def parse_header(answer: str) -> dict:
    """{'outcome': ..., 'cause': ..., 'fulfilable': ...} from the fixed answer format (None if missing)."""
    found = {k.lower(): v.strip().lower() for k, v in HEADER.findall(answer or "")}
    return {k: found.get(k) for k in ("outcome", "cause", "fulfilable")}
