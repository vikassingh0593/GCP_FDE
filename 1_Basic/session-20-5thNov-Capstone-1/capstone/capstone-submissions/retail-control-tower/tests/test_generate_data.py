"""data/generate_data.py: same rows on every run, only the times move, planted facts hold."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import load_generate_data

gd = load_generate_data()
T1 = datetime(2026, 11, 22, 3, 30, tzinfo=timezone.utc)   # 09:00 IST
T2 = datetime(2027, 6, 1, 17, 45, tzinfo=timezone.utc)


def _parse(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _is_time(value) -> bool:
    return isinstance(value, str) and len(value) == 20 and value.endswith("Z") and value[10] == "T"


def test_planted_facts_hold():
    gd.check(gd.build_tables(T1), T1)          # raises AssertionError if a scenario broke


def test_only_times_move_between_runs():
    a, b = gd.build_tables(T1), gd.build_tables(T2)
    assert a.keys() == b.keys()
    for name in a:
        assert len(a[name]) == len(b[name]), name
        for row_a, row_b in zip(a[name], b[name]):
            for column in row_a:
                va, vb = row_a[column], row_b[column]
                if _is_time(va):
                    assert T1 - _parse(va) == T2 - _parse(vb), (name, column)   # same offset from T
                else:
                    assert va == vb, (name, column)


def test_columns_match_schemas():
    tables = gd.build_tables(T1)
    for name, rows in tables.items():
        columns = [c[0] for c in gd.SCHEMAS[name]]
        assert all(list(r) == columns or set(r) == set(columns) for r in rows), name


def test_sensitive_columns_only_in_orders():
    sensitive = {"customer_name", "customer_phone", "shipping_address"}
    for name, schema in gd.SCHEMAS.items():
        names = {c[0] for c in schema}
        if name != "orders":
            assert not names & sensitive, name


def test_no_time_is_after_T_except_promises():
    """Nothing can have happened in the future; only promised delivery times may be ahead of T."""
    for name, rows in gd.build_tables(T1).items():
        for row in rows:
            for column, value in row.items():
                if _is_time(value) and column != "promised_delivery_at":
                    assert _parse(value) <= T1, (name, row.get("order_id") or row.get("event_id"), column)


@pytest.mark.parametrize("hours_after_load", [0, 4, 5])
def test_healthy_orders_not_overdue_within_demo_window(hours_after_load):
    """With the 5-hour freshness setting, no healthy order passes its promise during a session."""
    healthy = {"ORD-78401", "ORD-78402", "ORD-78403", "ORD-78404", "ORD-78405", "ORD-78406",
               "ORD-78431", "ORD-78446", "ORD-78447", "ORD-78471"}
    now = T1 + timedelta(hours=hours_after_load)
    for order in gd.build_tables(T1)["orders"]:
        if order["order_id"] in healthy and order["status"] != "DELIVERED":
            assert _parse(order["promised_delivery_at"]) > now, order["order_id"]
