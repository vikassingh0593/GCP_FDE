from app.evidence import EvidenceRegister

def test_evidence_ids_and_provenance():
    r=EvidenceRegister()
    a=r.add("GET_ORDER","order-service","SUCCESS",{"x":1})
    b=r.add("CHECK_INVENTORY","inventory-service","SUCCESS",{"x":2})
    assert a.evidence_id=="EV-001"
    assert b.evidence_id=="EV-002"
    assert r.successful_actions()=={"GET_ORDER","CHECK_INVENTORY"}
