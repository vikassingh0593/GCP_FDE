from app.contracts import Action, NextAction
from app.evidence import EvidenceRegister
from app.policy import RuntimePolicy

def d(action):
    return NextAction(next_action=action, reason="test", confidence=.8)

def test_premature_synthesis_rejected():
    p=RuntimePolicy(); e=EvidenceRegister()
    assert not p.evaluate(d(Action.SYNTHESIZE),e,0).allowed

def test_synthesis_after_minimum_evidence():
    p=RuntimePolicy(); e=EvidenceRegister()
    e.add("GET_ORDER","order","SUCCESS",{})
    e.add("CHECK_INVENTORY","inventory","SUCCESS",{})
    assert p.evaluate(d(Action.SYNTHESIZE),e,2).allowed

def test_tool_budget():
    p=RuntimePolicy(); p.max_tool_calls=1
    e=EvidenceRegister()
    assert not p.evaluate(d(Action.GET_ORDER),e,1).allowed

def test_repetition_limit():
    p=RuntimePolicy(); p.max_same_action=1
    e=EvidenceRegister()
    e.add("GET_ORDER","order","SUCCESS",{})
    assert not p.evaluate(d(Action.GET_ORDER),e,1).allowed

def test_safe_escalation_allowed():
    p=RuntimePolicy(); e=EvidenceRegister()
    assert p.evaluate(d(Action.ESCALATE),e,0).allowed
