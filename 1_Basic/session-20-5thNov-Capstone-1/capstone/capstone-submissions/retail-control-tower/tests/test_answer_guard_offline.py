"""orchestrator/answer_guard.py: header claims the evidence doesn't support are corrected by code."""

from __future__ import annotations

from orchestrator.answer_guard import check
from orchestrator.runtime import parse_header


def trace(tools=(), details=(), termination="NORMAL"):
    return {"termination": termination, "tools": list(tools), "details": list(details)}


ORDER = {"tool": "get_order", "outcome": "ok", "freshness": "fresh"}
ORDER_D = {"tool": "get_order", "order_id": "ORD-1", "shipped": False, "overdue": True, "payment_hold": False}
FUL_OK = {"tool": "check_fulfilment", "outcome": "ok", "freshness": "fresh"}
FUL_ERR = {"tool": "check_fulfilment", "outcome": "error", "freshness": "n/a"}


def a2a(verdict, reason):
    return {"tool": "check_fulfilment", "a2a": "fulfilment_specialist", "outcome": "ok", "verdict": verdict,
            "reason": reason}


def run(answer, *traces):
    text, header, fixes = check(answer, parse_header(answer), list(traces))
    return text, header, fixes


def test_a_supported_answer_is_left_alone():
    answer = "OUTCOME: cause_named\nCAUSE: inventory_shortage\nFULFILABLE: no\nANSWER: 7 of 40."
    text, header, fixes = run(answer, trace([ORDER, FUL_OK], [ORDER_D, a2a("no", "true_shortage")]))
    assert fixes == [] and text == answer


def test_stock_claim_while_the_specialist_was_down_is_corrected():           # eval R02
    answer = "OUTCOME: cause_named\nCAUSE: recent_change\nFULFILABLE: no_under_current_rule\nANSWER: x"
    text, header, fixes = run(answer, trace(
        [ORDER, FUL_ERR], [ORDER_D, {"tool": "compare_before_after_change", "pattern": "consistent_with_change"}]))
    assert header == {"outcome": "partial", "cause": "recent_change", "fulfilable": "unknown"}
    assert "CHECKED BY CODE:" in text and "FULFILABLE: unknown" in text


def test_cause_without_its_proof_becomes_check_next():
    answer = "OUTCOME: cause_named\nCAUSE: recent_change\nFULFILABLE: yes\nANSWER: x"
    text, header, fixes = run(answer, trace([ORDER, FUL_OK], [ORDER_D, a2a("yes", "enough_stock"),
                              {"tool": "compare_before_after_change", "pattern": "no_clear_pattern"}]))
    assert header["cause"] == "none" and header["outcome"] == "check_next" and header["fulfilable"] == "yes"


def test_fulfilable_must_agree_with_the_verdict():
    answer = "OUTCOME: cause_named\nCAUSE: allocation_reserved\nFULFILABLE: not_now\nANSWER: x"
    _, header, _ = run(answer, trace([ORDER, FUL_OK], [ORDER_D, a2a("no", "reserved_stock")]))
    assert header["fulfilable"] == "no" and header["cause"] == "allocation_reserved"


def test_stock_claim_without_any_check_is_unknown():
    answer = "OUTCOME: cause_named\nCAUSE: payment_hold\nFULFILABLE: yes\nANSWER: x"
    _, header, _ = run(answer, trace([ORDER], [dict(ORDER_D, payment_hold=True)]))
    assert header == {"outcome": "cause_named", "cause": "payment_hold", "fulfilable": "unknown"}


def test_overdue_order_is_never_no_problem_and_missing_header_is_added():
    _, header, _ = run("OUTCOME: no_problem\nCAUSE: none\nFULFILABLE: not_applicable", trace([ORDER], [ORDER_D]))
    assert header["outcome"] == "check_next"
    text, header, fixes = run("The order is fine.", trace([ORDER], [ORDER_D]))
    assert text.startswith("OUTCOME: partial") and len(fixes) == 3


def test_stopped_run_cannot_claim_a_cause():
    answer = "OUTCOME: cause_named\nCAUSE: inventory_shortage\nFULFILABLE: no"
    _, header, _ = run(answer, trace([ORDER, FUL_OK], [ORDER_D, a2a("no", "true_shortage")],
                                     termination="TOOL_BUDGET_EXCEEDED"))
    assert header["outcome"] == "partial" and header["cause"] == "inventory_shortage"


def test_resumed_run_uses_the_parent_run_evidence():
    parent = trace([ORDER, FUL_OK], [ORDER_D, a2a("no", "true_shortage")])
    resumed = trace([{"tool": "escalate_case", "outcome": "not_run"}])
    answer = "OUTCOME: cause_named\nCAUSE: inventory_shortage\nFULFILABLE: no"
    assert run(answer, parent, resumed)[2] == []
