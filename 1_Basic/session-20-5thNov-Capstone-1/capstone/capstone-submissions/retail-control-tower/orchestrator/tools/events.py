"""Carrier events, warehouse events and the change log: live state, read as structured data.

These are never embedded (Gate 1): exact times decide the answer, and the order
of events matters. Every result carries hours computed here, so the model
compares numbers instead of doing date arithmetic.

compare_before_after_change is the deterministic half of the change runbook
(RB-CHG-006): it counts failures before and after a change at the change's
scope. Timing alone is not evidence; the before/after pattern is.
"""

from __future__ import annotations

from common import config, results
from common.clients import query_rows
from common.freshness import hours_ago, hours_between
from common.inputs import CHANGE_ID, ORDER_ID, WAREHOUSE_ID, clean_id, positive_int

# A change to allocation rules shows up as orders failing allocation. Payment holds (ON_HOLD) are
# left out: a credit hold placed after a warehouse change is not evidence about that change.
FAILED = ("ALLOCATION_PENDING",)
MIN_BEFORE = 2                 # orders placed before the change: fewer is not a comparison
FEED_LAG_HOURS = 2.0           # RB-CAR-003 check 2: report a lag over 2 hours


def _p(name, value, kind="STRING"):
    from google.cloud import bigquery
    return bigquery.ScalarQueryParameter(name, kind, value)


def get_carrier_events(order_id: str) -> dict:
    """All carrier tracking events for one order, oldest first, with feed lag and time since the last event.

    Use for shipped orders: where is it, is there an exception code (e.g. WX-HOLD),
    has the carrier gone silent, does the carrier agree the order was picked up. Read-only.
    """
    order_id = clean_id(order_id)
    if not ORDER_ID.match(order_id):
        return results.error("bigquery:carrier_events", "invalid_argument", "order_id must look like ORD-12345")
    rows = query_rows(f"""
        SELECT event_id, carrier, tracking_number, event_code, exception_code, description, location,
               event_at, received_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['carrier_events'])}`
        WHERE order_id = @order_id ORDER BY event_at, event_id""", [_p("order_id", order_id)], "get_carrier_events")
    if not rows:
        return results.not_found("CAR", order_id, "bigquery:carrier_events",
                                 f"No carrier events for {order_id} (not handed to a carrier, or no feed yet).")
    now = results.now_utc()
    events = []
    for r in rows:
        lag = hours_between(r["event_at"], r["received_at"])
        events.append({"event_id": r["event_id"], "event_code": r["event_code"], "exception_code": r["exception_code"],
                       "description": r["description"], "location": r["location"],
                       "event_hours_ago": hours_ago(r["event_at"], now),
                       "received_hours_ago": hours_ago(r["received_at"], now),
                       "feed_lag_hours": lag, "late_event": bool(lag and lag > FEED_LAG_HOURS)})
    latest = events[-1]
    codes = {e["event_code"] for e in events}
    delivered = "DELIVERED" in codes
    silent = (not delivered and latest["event_hours_ago"] is not None
              and latest["event_hours_ago"] > config.CARRIER_SILENCE_HOURS)
    data = {
        "order_id": order_id, "carrier": rows[0]["carrier"], "tracking_number": rows[0]["tracking_number"],
        "events": events,
        "latest_event": latest["event_code"], "latest_exception_code": latest["exception_code"],
        "latest_location": latest["location"], "hours_since_latest_event": latest["event_hours_ago"],
        "has_pickup": "PICKED_UP" in codes, "delivered": delivered,
        # A delivered parcel is not "silent": no more events are expected.
        "silent_over_hours": config.CARRIER_SILENCE_HOURS if silent else None,
    }
    out = results.ok("CAR", order_id, "bigquery:carrier_events", data,
                     source_time=max(r["received_at"] for r in rows), now=now)
    out["_trace"] = {"latest_exception_code": latest["exception_code"], "has_pickup": data["has_pickup"],
                     "silent": bool(data["silent_over_hours"])}
    return out


def get_warehouse_events(warehouse_id: str, lookback_hours: int = 168) -> dict:
    """Disruptions at one warehouse (outages, closed docks, labour shortages) that are open or ended
    within the lookback. ongoing = no end time yet. Read-only.
    """
    warehouse_id = clean_id(warehouse_id)
    if not WAREHOUSE_ID.match(warehouse_id):
        return results.error("bigquery:warehouse_events", "invalid_argument", "warehouse_id must look like WH-BLR-01")
    lookback_hours = positive_int(lookback_hours, maximum=24 * 30) or 168
    rows = query_rows(f"""
        SELECT event_id, event_type, severity, description, started_at, ended_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['warehouse_events'])}`
        WHERE warehouse_id = @warehouse_id
          AND (ended_at IS NULL OR ended_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR))
        ORDER BY started_at""", [_p("warehouse_id", warehouse_id), _p("hours", lookback_hours, "INT64")],
        "get_warehouse_events")
    now = results.now_utc()
    events = [{"event_id": r["event_id"], "event_type": r["event_type"], "severity": r["severity"],
               "description": r["description"], "started_hours_ago": hours_ago(r["started_at"], now),
               "ended_hours_ago": hours_ago(r["ended_at"], now), "ongoing": r["ended_at"] is None,
               "evidence_id": results.evidence_id("WHE", r["event_id"], r["started_at"])} for r in rows]
    out = results.ok("WHE", f"{warehouse_id}/{lookback_hours}h", "bigquery:warehouse_events",
                     {"warehouse_id": warehouse_id, "lookback_hours": lookback_hours, "events": events,
                      "open_events": [e["event_id"] for e in events if e["ongoing"]]}, now=now)
    out["_trace"] = {"warehouse_id": warehouse_id, "open_events": [e["event_id"] for e in events if e["ongoing"]]}
    return out


def get_recent_changes(scope: str, lookback_days: int = 14) -> dict:
    """Config and system changes in the lookback for one scope: a warehouse ID (WH-BOM-01),
    a carrier ("carrier:Blue Dart"), or "ALL". Changes with scope ALL are always included.

    A change that happened before a delay is a lead, not a cause: confirm it with
    compare_before_after_change. Read-only.
    """
    scope = (scope or "").strip()
    if not scope:
        return results.error("bigquery:change_log", "invalid_argument", "scope is required (e.g. WH-BOM-01)")
    lookback_days = positive_int(lookback_days, maximum=60) or 14
    rows = query_rows(f"""
        SELECT change_id, changed_at, system, scope, change_type, description, changed_by, ticket
        FROM `{config.table_id(config.OPERATIONAL_TABLES['change_log'])}`
        WHERE (LOWER(scope) = LOWER(@scope) OR scope = 'ALL')
          AND changed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
        ORDER BY changed_at DESC""", [_p("scope", scope), _p("days", lookback_days, "INT64")], "get_recent_changes")
    now = results.now_utc()
    changes = [{"change_id": r["change_id"], "hours_ago": hours_ago(r["changed_at"], now), "system": r["system"],
                "scope": r["scope"], "change_type": r["change_type"], "description": r["description"],
                "owner": r["changed_by"], "ticket": r["ticket"],
                "evidence_id": results.evidence_id("CHG", r["change_id"], r["changed_at"])} for r in rows]
    return results.ok("CHL", f"{scope}/{lookback_days}d", "bigquery:change_log",
                      {"scope": scope, "lookback_days": lookback_days, "changes": changes}, now=now)


# The change runbook is fetched by code whenever a before/after comparison runs. Run 5 (2026-11-24):
# the model reworded its own search and missed the change runbook in A06 and A07, though the cause
# was right. Searched by text and register tags, never by document ID: a new version of the
# runbook, or a new ID, is found through the register like any other search.
CHANGE_RUNBOOK_QUERY = "change-related incident before and after comparison rollback who decides"
CHANGE_RUNBOOK_CARDS = 2


def change_runbook() -> tuple[dict, dict | None]:
    """The current change runbook sections for the comparison, and the search trace.

    Never breaks the comparison: if the search fails, the comparison is still
    returned, with a note that the runbook could not be fetched.
    """
    from orchestrator.retrieval.search import search
    try:
        found = search(CHANGE_RUNBOOK_QUERY, doc_type="runbook", exception_type="recent_change")
    except Exception as exc:  # noqa: BLE001 - the comparison is the evidence; the runbook is guidance
        return {"status": "error", "note": f"Change runbook could not be fetched ({type(exc).__name__}); "
                                           "use search_knowledge."}, None
    trace = found.get("_trace")              # read, not pop: on a cache miss this dict IS the cached entry
    if found.get("status") != "ok":
        return {"status": found.get("status"), "note": found.get("message") or "No change runbook found; "
                                                                               "use search_knowledge."}, trace
    cards = (found.get("data") or {}).get("results", [])[:CHANGE_RUNBOOK_CARDS]
    return {"status": "ok", "evidence_id": found.get("evidence_id"), "results": cards}, trace


def compare_before_after_change(change_id: str, window_hours: int = 48) -> dict:
    """The before/after test for one warehouse-scoped change (RB-CHG-006): orders at the change's
    warehouse placed in the window before vs after it, and how many failed in each group.

    pattern = "consistent_with_change" only when at least 2 orders placed after the
    change failed with the same reason code, none placed before it failed with that
    code, and at least 2 orders were placed before it. The result also carries the
    current change runbook (who decides a rollback, what to check): cite it from
    there. Read-only.
    """
    change_id = clean_id(change_id)
    if not CHANGE_ID.match(change_id):
        return results.error("bigquery:change_log", "invalid_argument", "change_id must look like CHG-1234")
    window_hours = max(6, positive_int(window_hours, maximum=24 * 7) or 48)
    changes = query_rows(f"""
        SELECT change_id, changed_at, scope, description, changed_by
        FROM `{config.table_id(config.OPERATIONAL_TABLES['change_log'])}` WHERE change_id = @id""",
        [_p("id", change_id)], "compare_before_after_change")
    if not changes:
        return results.not_found("CMP", change_id, "bigquery:change_log", f"Change {change_id} does not exist.")
    change = changes[0]
    if not WAREHOUSE_ID.match(change["scope"] or ""):
        return results.ok("CMP", change_id, "bigquery:change_log",
                          {"change_id": change_id, "scope": change["scope"], "pattern": "not_applicable",
                           "note": "Not a warehouse-scoped change, so there is no warehouse before/after group."})

    orders = query_rows(f"""
        SELECT order_id, status, status_reason_code, placed_at, extracted_at
        FROM `{config.table_id(config.OPERATIONAL_TABLES['orders'])}`
        WHERE warehouse_id = @warehouse
          AND placed_at BETWEEN TIMESTAMP_SUB(@at, INTERVAL @w HOUR) AND TIMESTAMP_ADD(@at, INTERVAL @w HOUR)
        ORDER BY placed_at""",
        [_p("warehouse", change["scope"]), _p("at", change["changed_at"], "TIMESTAMP"), _p("w", window_hours, "INT64")],
        "compare_before_after_change")

    # Count only the failure the change could cause: the reason code most common among failing orders
    # placed after it. A stock shortage (ALLOC-E101) at the same warehouse is not evidence about a rule change.
    after_rows = [o for o in orders if o["placed_at"] >= change["changed_at"]]
    codes = [o["status_reason_code"] for o in after_rows if o["status"] in FAILED and o["status_reason_code"]]
    focus = max(set(codes), key=codes.count) if codes else None

    def group(items):
        failed = [o["order_id"] for o in items if o["status"] in FAILED and o["status_reason_code"] == focus]
        return {"orders": [o["order_id"] for o in items], "failed": failed,
                "reason_codes": sorted({o["status_reason_code"] for o in items if o["status_reason_code"]}),
                "count": len(items), "failed_count": len(failed)}

    before = group([o for o in orders if o["placed_at"] < change["changed_at"]])
    after = group([o for o in orders if o["placed_at"] >= change["changed_at"]])
    consistent = after["failed_count"] >= 2 and before["failed_count"] == 0 and before["count"] >= MIN_BEFORE
    pattern = ("consistent_with_change" if consistent else
               "insufficient_before_group" if before["count"] < MIN_BEFORE else "no_clear_pattern")
    now = results.now_utc()
    out = results.ok("CMP", change_id, "bigquery:orders+change_log", {
        "change_id": change_id, "warehouse_id": change["scope"], "change_hours_ago": hours_ago(change["changed_at"], now),
        "reason_code_compared": focus,
        "description": change["description"], "owner": change["changed_by"], "window_hours": window_hours,
        "before": before, "after": after, "pattern": pattern,
        "note": "A pattern consistent with the change makes it the likely cause; the rollback decision "
                "belongs to the change owner.",
    }, source_time=min((o["extracted_at"] for o in orders), default=None),
        max_age_minutes=config.ORDER_MAX_AGE_MINUTES if orders else None, now=now)
    runbook, search_trace = change_runbook()
    out["data"]["runbook"] = runbook
    out["_trace"] = {"change_id": change_id, "pattern": pattern,
                     "docs": (search_trace or {}).get("docs", []), "runbook_search": search_trace}
    return out
