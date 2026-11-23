"""common/: result contract, freshness, masking, request context, citation IDs."""

from __future__ import annotations

from datetime import timedelta

import pytest

from common import results
from common.freshness import age_minutes, freshness, hours_ago
from common.harness import cited_evidence_ids, from_metadata, RequestContext
from common.masking import mask, pseudonymize
from fakes import NOW, ago


def test_evidence_ids_are_stable_and_change_with_source_time():
    a = results.evidence_id("INV", "WH-BLR-01/SKU-74512", ago(minutes=10))
    assert a == results.evidence_id("INV", "WH-BLR-01/SKU-74512", ago(minutes=10))
    assert a != results.evidence_id("INV", "WH-BLR-01/SKU-74512", ago(minutes=20))
    assert a.startswith("EV-INV-WH-BLR-01/SKU-74512-")


def test_evidence_id_is_one_token_even_when_the_key_has_spaces():
    eid = results.evidence_id("CHL", "carrier:Blue Dart/14d")
    assert " " not in eid and eid.startswith("EV-CHL-carrier:Blue_Dart/14d-")
    assert cited_evidence_ids(f"No service change [{eid}].") == [eid]


def test_freshness_is_decided_by_code():
    assert freshness(ago(minutes=10), 300, NOW) == "fresh"
    assert freshness(ago(days=2), 300, NOW) == "stale"            # S7
    assert freshness(None, 300, NOW) == "stale"                     # no source time: can't prove fresh
    assert freshness(NOW + timedelta(hours=2), 300, NOW) == "stale"  # from the future: not trusted
    assert age_minutes(ago(minutes=90), NOW) == 90
    assert hours_ago(ago(hours=20), NOW) == 20.0


def test_ok_result_carries_source_time_and_freshness():
    out = results.ok("ORD", "ORD-1", "bigquery:orders", {"x": 1}, source_time=ago(days=2), max_age_minutes=300)
    assert out["status"] == "ok" and out["freshness"] == "stale" and out["age_minutes"] == 2880


def test_error_results_say_whether_retry_helps():
    assert results.error("x", "timeout", "slow")["retryable"] is True
    assert results.error("x", "invalid_argument", "bad")["retryable"] is False
    assert results.error("x", "made_up", "?")["error_type"] == "internal"


def test_nested_evidence_ids_are_collected():
    value = {"evidence_id": "EV-FUL-ORD-1-aaaaaa", "data": {"evidence_ids": ["EV-INV-X-bbbbbb"],
                                                            "options": [{"evidence_id": "EV-INV-Y-cccccc"}]}}
    assert results.collect_evidence_ids(value) == ["EV-FUL-ORD-1-aaaaaa", "EV-INV-X-bbbbbb", "EV-INV-Y-cccccc"]


def test_masking_hides_customer_details_before_logging():
    masked = mask({"customer_name": "Ananya Rao", "note": "call +91 98000 78401 or a@b.com",
                   "nested": [{"shipping_address": "Flat 302"}], "order_id": "ORD-78401"})
    assert masked["customer_name"] == "[masked]" and masked["nested"][0]["shipping_address"] == "[masked]"
    assert "98000" not in masked["note"] and "a@b.com" not in masked["note"]
    assert masked["order_id"] == "ORD-78401"
    assert pseudonymize("A@B.com", "salt") == pseudonymize("a@b.com ", "salt") != pseudonymize("a@b.com", "other")


def test_request_context_is_read_from_both_runtimes():
    ctx = RequestContext.create(user="analyst_1", session_id="s_1")
    direct = from_metadata(ctx.to_metadata())                         # orchestrator: RunConfig.custom_metadata
    over_a2a = from_metadata({"a2a_metadata": ctx.to_metadata()})     # specialist: forwarded over A2A
    assert direct.correlation_id == over_a2a.correlation_id == ctx.correlation_id
    assert over_a2a.user == "analyst_1"
    assert from_metadata({}) is None and from_metadata({"correlation_id": "c"}) is None   # no user: refused


@pytest.mark.parametrize("text,expected", [
    ("7 available [EV-INV-WH-BLR-01/SKU-74512-3f9a1c].", ["EV-INV-WH-BLR-01/SKU-74512-3f9a1c"]),
    ("[EV-ORD-ORD-78421-0a1b2c], [EV-DOC-RB-CAR-003@v4#c002-abcdef]",
     ["EV-ORD-ORD-78421-0a1b2c", "EV-DOC-RB-CAR-003@v4#c002-abcdef"]),
    ("no ids here", []),
])
def test_cited_evidence_ids(text, expected):
    assert cited_evidence_ids(text) == expected
