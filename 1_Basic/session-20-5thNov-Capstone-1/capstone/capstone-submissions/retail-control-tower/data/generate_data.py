#!/usr/bin/env python3
"""Sample data for the Retail Order Exception Control Tower capstone.

Every run writes exactly the same rows. Only the times move: each time is
stored as an offset from T, the moment the script runs (UTC, rounded down to
the minute). Fresh records are always minutes old and stale records are always
2 days old, whatever day you run it.

    python data/generate_data.py                               # T = now
    python data/generate_data.py --as-of 2026-11-15T09:00:00Z  # fixed T (tests, replaying a bad answer)

Writes (overwrites on every run):
    data/tables/<table>.csv     orders, inventory, carrier_events, warehouse_events, change_log
    data/tables/manifest.json   T and the row counts
    data/schemas/<table>.json   BigQuery schema for each table, for the load step

Not touched here:
    data/docs/                  runbooks and postmortems (static; history doesn't go stale)
    BigQuery / GCS              the separate truncate-and-load script does that

The answer key for every planted scenario is data/scenarios.md. If you change a
row, update scenarios.md and the checks at the bottom of this file.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
TABLES_DIR = DATA_DIR / "tables"
SCHEMAS_DIR = DATA_DIR / "schemas"

# (column, BigQuery type, mode, description). Column order = CSV column order.
SCHEMAS: dict[str, list[tuple[str, str, str, str]]] = {
    "orders": [
        ("order_id", "STRING", "REQUIRED", "Order ID, e.g. ORD-78421"),
        ("order_type", "STRING", "REQUIRED", "B2C or B2B"),
        ("customer_name", "STRING", "REQUIRED", "SENSITIVE. Customer or business name"),
        ("customer_phone", "STRING", "REQUIRED", "SENSITIVE. Contact phone"),
        ("shipping_address", "STRING", "REQUIRED", "SENSITIVE. Full delivery address"),
        ("shipping_city", "STRING", "REQUIRED", "Delivery city"),
        ("sku", "STRING", "REQUIRED", "Product SKU (one line per order)"),
        ("quantity", "INTEGER", "REQUIRED", "Units ordered"),
        ("warehouse_id", "STRING", "REQUIRED", "Assigned warehouse"),
        ("status", "STRING", "REQUIRED", "ALLOCATION_PENDING, ALLOCATED, PICKING, PACKED, SHIPPED, DELIVERED or ON_HOLD"),
        ("status_reason_code", "STRING", "NULLABLE", "Order-system reason code, e.g. ALLOC-E101, ALLOC-E107, PAY-H201"),
        ("payment_status", "STRING", "REQUIRED", "SENSITIVE. AUTHORIZED, CAPTURED or CREDIT_HOLD"),
        ("carrier", "STRING", "NULLABLE", "Carrier, once a label exists"),
        ("tracking_number", "STRING", "NULLABLE", "Carrier tracking number, once a label exists"),
        ("placed_at", "TIMESTAMP", "REQUIRED", "When the customer placed the order"),
        ("promised_delivery_at", "TIMESTAMP", "REQUIRED", "Delivery time promised to the customer"),
        ("last_updated_at", "TIMESTAMP", "REQUIRED", "When the order record last changed"),
        ("extracted_at", "TIMESTAMP", "REQUIRED", "When this row was read from the order system (freshness proof)"),
    ],
    "inventory": [
        ("warehouse_id", "STRING", "REQUIRED", "Warehouse"),
        ("sku", "STRING", "REQUIRED", "Product SKU"),
        ("on_hand", "INTEGER", "REQUIRED", "Units physically in the warehouse"),
        ("reserved", "INTEGER", "REQUIRED", "Units held for already-allocated orders"),
        ("available", "INTEGER", "REQUIRED", "on_hand minus reserved: what a new order can use"),
        ("snapshot_at", "TIMESTAMP", "REQUIRED", "When the stock ledger snapshot was taken (freshness proof)"),
    ],
    "carrier_events": [
        ("event_id", "STRING", "REQUIRED", "Carrier event ID"),
        ("order_id", "STRING", "REQUIRED", "Order ID"),
        ("tracking_number", "STRING", "REQUIRED", "Carrier tracking number"),
        ("carrier", "STRING", "REQUIRED", "Carrier name"),
        ("event_code", "STRING", "REQUIRED", "MANIFESTED, PICKED_UP, IN_TRANSIT, ARRIVED_AT_HUB, EXCEPTION, OUT_FOR_DELIVERY or DELIVERED"),
        ("exception_code", "STRING", "NULLABLE", "Set when event_code is EXCEPTION, e.g. WX-HOLD"),
        ("description", "STRING", "REQUIRED", "Carrier's event text"),
        ("location", "STRING", "REQUIRED", "Where the event happened"),
        ("event_at", "TIMESTAMP", "REQUIRED", "When the event happened"),
        ("received_at", "TIMESTAMP", "REQUIRED", "When our system received it (can be hours later)"),
    ],
    "warehouse_events": [
        ("event_id", "STRING", "REQUIRED", "Warehouse event ID"),
        ("warehouse_id", "STRING", "REQUIRED", "Warehouse"),
        ("event_type", "STRING", "REQUIRED", "SYSTEM_DOWN, DOCK_CLOSED, POWER_OUTAGE or LABOUR_SHORTAGE"),
        ("severity", "STRING", "REQUIRED", "LOW, MEDIUM or HIGH"),
        ("description", "STRING", "REQUIRED", "What is happening"),
        ("started_at", "TIMESTAMP", "REQUIRED", "When it started"),
        ("ended_at", "TIMESTAMP", "NULLABLE", "When it ended; empty means still ongoing"),
    ],
    "change_log": [
        ("change_id", "STRING", "REQUIRED", "Change ID"),
        ("changed_at", "TIMESTAMP", "REQUIRED", "When the change went live"),
        ("system", "STRING", "REQUIRED", "System that changed"),
        ("scope", "STRING", "REQUIRED", "Warehouse ID, carrier:<name> or ALL"),
        ("change_type", "STRING", "REQUIRED", "CONFIG, UPGRADE or DATA"),
        ("description", "STRING", "REQUIRED", "What changed"),
        ("changed_by", "STRING", "REQUIRED", "Owning team"),
        ("ticket", "STRING", "REQUIRED", "Release ticket"),
    ],
}


def fmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_tables(T: datetime) -> dict[str, list[dict]]:
    """All rows, with every time written as an offset from T."""

    def ago(d: float = 0, h: float = 0, m: float = 0) -> str:
        return fmt(T - timedelta(days=d, hours=h, minutes=m))

    def ahead(d: float = 0, h: float = 0, m: float = 0) -> str:
        return fmt(T + timedelta(days=d, hours=h, minutes=m))

    # ------------------------------------------------------------------ orders
    def order(order_id, order_type, name, address, city, sku, qty, wh, status, payment,
              placed, promised, updated, reason=None, carrier=None, tracking=None):
        return {
            "order_id": order_id, "order_type": order_type, "customer_name": name,
            "customer_phone": f"+91 98000 {order_id[-5:]}",  # synthetic, never a real number
            "shipping_address": address, "shipping_city": city, "sku": sku, "quantity": qty,
            "warehouse_id": wh, "status": status, "status_reason_code": reason,
            "payment_status": payment, "carrier": carrier, "tracking_number": tracking,
            "placed_at": placed, "promised_delivery_at": promised, "last_updated_at": updated,
            "extracted_at": ago(m=5),
        }

    orders = [
        # --- healthy: shipped, delivered or moving normally
        order("ORD-78401", "B2C", "Ananya Rao", "Flat 302, Palm Grove Apts, 7th Main, HSR Layout, Bengaluru 560102",
              "Bengaluru", "SKU-10234", 2, "WH-BLR-01", "DELIVERED", "CAPTURED",
              ago(h=120), ago(h=48), ago(h=73), carrier="Delhivery", tracking="DLV4410023801"),
        order("ORD-78402", "B2C", "Rohit Mehta", "B-14, Shanti Nagar, Tonk Road, Jaipur 302018",
              "Jaipur", "SKU-20417", 1, "WH-DEL-01", "SHIPPED", "CAPTURED",
              ago(h=40), ahead(h=24), ago(h=24), carrier="Blue Dart", tracking="BD70023318802"),
        order("ORD-78403", "B2C", "Sravani Reddy", "D.No 40-1-12, Labbipet, Vijayawada 520010",
              "Vijayawada", "SKU-30982", 1, "WH-HYD-01", "SHIPPED", "CAPTURED",
              ago(h=30), ahead(h=16), ago(h=20), carrier="Delhivery", tracking="DLV4410023803"),
        order("ORD-78404", "B2C", "Kunal Deshpande", "12 Sai Residency, Baner Road, Pune 411045",
              "Pune", "SKU-41150", 3, "WH-BOM-01", "DELIVERED", "CAPTURED",
              ago(h=144), ago(h=96), ago(h=98), carrier="Delhivery", tracking="DLV4410023804"),
        order("ORD-78405", "B2C", "Arjun Malhotra", "Tower 6, Flat 1104, Sector 54, Gurugram 122011",
              "Gurugram", "SKU-52076", 1, "WH-DEL-01", "ALLOCATED", "CAPTURED",
              ago(h=3), ahead(h=72), ago(h=2, m=50)),
        order("ORD-78406", "B2C", "Kavya Nair", "45, 2nd Cross, Indiranagar, Bengaluru 560038",
              "Bengaluru", "SKU-85023", 4, "WH-BLR-01", "PACKED", "CAPTURED",
              ago(h=24), ahead(h=48), ago(h=2), carrier="Delhivery", tracking="DLV4410023806"),

        # --- S1 inventory shortage (the brief's order)
        order("ORD-78421", "B2B", "Annapurna Caterers", "No. 8, Temple Road, Saraswathipuram, Mysuru 570009",
              "Mysuru", "SKU-74512", 40, "WH-BLR-01", "ALLOCATION_PENDING", "AUTHORIZED",
              ago(h=48), ago(h=4), ago(h=47, m=50), reason="ALLOC-E101"),

        # --- S2 allocation: stock on hand but reserved by the bulk order ORD-78431
        order("ORD-78430", "B2B", "Nexa Cowork LLP", "Plot 21, Sector 62, Noida 201309",
              "Noida", "SKU-63301", 12, "WH-DEL-01", "ALLOCATION_PENDING", "AUTHORIZED",
              ago(h=20), ago(h=2), ago(h=19, m=50), reason="ALLOC-E101"),
        order("ORD-78431", "B2B", "Sharma Office Supplies Pvt Ltd", "22 Nehru Place, New Delhi 110019",
              "New Delhi", "SKU-63301", 45, "WH-DEL-01", "ALLOCATED", "CAPTURED",
              ago(h=26), ahead(h=48), ago(h=25, m=50)),

        # --- S3 carrier delay: weather hold at the Nagpur hub, event arrived 6h late
        order("ORD-78433", "B2C", "Farhan Qureshi", "Flat 5B, Banjara Heights, Road No. 12, Banjara Hills, Hyderabad 500034",
              "Hyderabad", "SKU-20417", 2, "WH-DEL-01", "SHIPPED", "CAPTURED",
              ago(h=54), ago(h=3), ago(h=46), carrier="Blue Dart", tracking="BD70023318833"),

        # --- S4 payment hold
        order("ORD-78436", "B2C", "Priya Sethi", "House 1187, Sector 21-B, Chandigarh 160022",
              "Chandigarh", "SKU-96140", 2, "WH-DEL-01", "ON_HOLD", "CREDIT_HOLD",
              ago(h=26), ago(h=2), ago(h=24), reason="PAY-H201"),

        # --- S5 warehouse disruption: Hyderabad WMS down since T-3h
        order("ORD-78440", "B2C", "Venkat Subramanian", "Plot 77, Kavuri Hills, Madhapur, Hyderabad 500081",
              "Hyderabad", "SKU-30982", 3, "WH-HYD-01", "PICKING", "CAPTURED",
              ago(h=8), ago(h=1), ago(h=4)),

        # --- S6 recent change: Mumbai allocation rule v2 at T-20h
        # control group: placed before the change, shipped normally
        order("ORD-78446", "B2C", "Neha Kulkarni", "Flat 9, Shivaji Park Road 3, Dadar West, Mumbai 400028",
              "Mumbai", "SKU-41150", 1, "WH-BOM-01", "SHIPPED", "CAPTURED",
              ago(h=30), ahead(h=18), ago(h=24), carrier="Delhivery", tracking="DLV4410023846"),
        order("ORD-78447", "B2C", "Siddharth Joshi", "A-402, Hiranandani Estate, Ghodbunder Road, Thane 400607",
              "Thane", "SKU-52076", 1, "WH-BOM-01", "SHIPPED", "CAPTURED",
              ago(h=26), ahead(h=24), ago(h=18), carrier="Delhivery", tracking="DLV4410023847"),
        # affected: placed after the change, stuck although stock exists
        order("ORD-78450", "B2C", "Aisha Khan", "Sector 17, Plot 4, Vashi, Navi Mumbai 400703",
              "Navi Mumbai", "SKU-41150", 2, "WH-BOM-01", "ALLOCATION_PENDING", "CAPTURED",
              ago(h=18), ago(h=2), ago(h=17, m=50), reason="ALLOC-E107"),
        order("ORD-78451", "B2C", "Rahul Patil", "Room 12, Laxmi Chawl, Lalbaug, Mumbai 400012",
              "Mumbai", "SKU-10234", 3, "WH-BOM-01", "ALLOCATION_PENDING", "CAPTURED",
              ago(h=15), ahead(h=9), ago(h=14, m=50), reason="ALLOC-E107"),
        order("ORD-78452", "B2C", "Pooja Shah", "Flat 701, Sea Breeze, Carter Road, Bandra West, Mumbai 400050",
              "Mumbai", "SKU-85023", 1, "WH-BOM-01", "ALLOCATION_PENDING", "CAPTURED",
              ago(h=11), ahead(h=13), ago(h=10, m=50), reason="ALLOC-E107"),
        order("ORD-78453", "B2C", "Imran Shaikh", "Shop-cum-flat 3, Kurla West, Mumbai 400070",
              "Mumbai", "SKU-52076", 1, "WH-BOM-01", "ALLOCATION_PENDING", "AUTHORIZED",
              ago(h=6), ahead(h=30), ago(h=5, m=50), reason="ALLOC-E107"),

        # --- S7 insufficient evidence: inventory snapshot is 2 days old
        order("ORD-78460", "B2C", "Deepak Verma", "KD-118, Kavi Nagar, Ghaziabad 201002",
              "Ghaziabad", "SKU-85023", 6, "WH-DEL-01", "ALLOCATION_PENDING", "CAPTURED",
              ago(h=72), ago(h=24), ago(h=71, m=50), reason="ALLOC-E101"),
        # --- S8 insufficient evidence: no inventory record at all for this SKU at the warehouse
        order("ORD-78462", "B2C", "Sunita Bansal", "House 233, Sector 15, Faridabad 121007",
              "Faridabad", "SKU-30982", 2, "WH-DEL-01", "ALLOCATION_PENDING", "CAPTURED",
              ago(h=50), ago(h=10), ago(h=49, m=50)),
        # --- S9 conflicting evidence: order says SHIPPED, carrier never picked it up
        order("ORD-78465", "B2C", "Harish Gowda", "88, 4th Block, Jayanagar, Bengaluru 560011",
              "Bengaluru", "SKU-63301", 1, "WH-BLR-01", "SHIPPED", "CAPTURED",
              ago(h=40), ago(h=6), ago(h=30), carrier="Delhivery", tracking="DLV4410023865"),
        # --- S10 insufficient evidence: carrier silent for 4 days
        order("ORD-78468", "B2C", "Lakshmi Narayanan", "14, 2nd Avenue, Besant Nagar, Chennai 600090",
              "Chennai", "SKU-96140", 1, "WH-HYD-01", "SHIPPED", "CAPTURED",
              ago(h=130), ago(h=48), ago(h=120), carrier="Blue Dart", tracking="BD70023318868"),

        # --- S11 the trap: looks like the Bangalore sync failure postmortem, real cause is reserved stock
        order("ORD-78470", "B2B", "Lakeview Residency", "Survey 41, Hennur Main Road, Bengaluru 560043",
              "Bengaluru", "SKU-20417", 10, "WH-BLR-01", "ALLOCATION_PENDING", "AUTHORIZED",
              ago(h=22), ago(h=1), ago(h=21, m=50), reason="ALLOC-E101"),
        order("ORD-78471", "B2B", "Grand Orchid Hotels Pvt Ltd", "1 Residency Road, Bengaluru 560025",
              "Bengaluru", "SKU-20417", 58, "WH-BLR-01", "ALLOCATED", "CAPTURED",
              ago(h=30), ahead(h=72), ago(h=29, m=50)),
    ]

    # --------------------------------------------------------------- inventory
    def stock(wh, sku, on_hand, reserved, snapshot):
        return {"warehouse_id": wh, "sku": sku, "on_hand": on_hand, "reserved": reserved,
                "available": on_hand - reserved, "snapshot_at": snapshot}

    blr, dlh, bom, hyd = ago(m=10), ago(m=12), ago(m=9), ago(m=11)  # fresh snapshots per warehouse
    inventory = [
        stock("WH-BLR-01", "SKU-10234", 140, 20, blr),
        stock("WH-BLR-01", "SKU-20417", 60, 58, blr),   # S11 trap: 58 held by ORD-78471
        stock("WH-BLR-01", "SKU-63301", 35, 5, blr),
        stock("WH-BLR-01", "SKU-74512", 7, 0, blr),     # S1 shortage: 7 available, 40 needed
        stock("WH-BLR-01", "SKU-85023", 90, 12, blr),
        stock("WH-DEL-01", "SKU-20417", 70, 15, dlh),
        stock("WH-DEL-01", "SKU-52076", 40, 6, dlh),
        stock("WH-DEL-01", "SKU-63301", 50, 45, dlh),   # S2 allocation: 45 held by ORD-78431
        stock("WH-DEL-01", "SKU-74512", 65, 10, dlh),   # S1 re-route option
        stock("WH-DEL-01", "SKU-85023", 20, 18, ago(d=2)),  # S7: STALE, 2 days old
        stock("WH-DEL-01", "SKU-96140", 80, 10, dlh),
        # S8: deliberately no WH-DEL-01 / SKU-30982 row
        stock("WH-BOM-01", "SKU-10234", 150, 10, bom),
        stock("WH-BOM-01", "SKU-41150", 200, 25, bom),
        stock("WH-BOM-01", "SKU-52076", 60, 4, bom),
        stock("WH-BOM-01", "SKU-85023", 75, 5, bom),
        stock("WH-HYD-01", "SKU-30982", 120, 30, hyd),  # S5: stock fine, warehouse can't pick
        stock("WH-HYD-01", "SKU-96140", 45, 5, hyd),
    ]

    # ---------------------------------------------------------- carrier events
    carrier_events: list[dict] = []

    def ev(order_id, code, description, location, event_at, received_at=None, exception=None):
        o = next(r for r in orders if r["order_id"] == order_id)
        carrier_events.append({
            "event_id": f"CE-{len(carrier_events) + 1:04d}", "order_id": order_id,
            "tracking_number": o["tracking_number"], "carrier": o["carrier"],
            "event_code": code, "exception_code": exception, "description": description,
            "location": location, "event_at": fmt(event_at),
            "received_at": fmt(received_at or event_at + timedelta(minutes=5)),
        })

    def t(h: float) -> datetime:  # h hours before T
        return T - timedelta(hours=h)

    ev("ORD-78401", "MANIFESTED", "Shipment label created", "WH-BLR-01 Bengaluru", t(100))
    ev("ORD-78401", "PICKED_UP", "Picked up from warehouse", "WH-BLR-01 Bengaluru", t(96))
    ev("ORD-78401", "IN_TRANSIT", "Departed Bengaluru hub", "Bengaluru hub", t(90))
    ev("ORD-78401", "OUT_FOR_DELIVERY", "Out for delivery", "HSR Layout delivery centre", t(76))
    ev("ORD-78401", "DELIVERED", "Delivered to customer", "Bengaluru", t(73))

    ev("ORD-78402", "MANIFESTED", "Shipment label created", "WH-DEL-01 Delhi", t(30))
    ev("ORD-78402", "PICKED_UP", "Picked up from warehouse", "WH-DEL-01 Delhi", t(24))
    ev("ORD-78402", "ARRIVED_AT_HUB", "Arrived at destination hub", "Jaipur hub", t(6))

    ev("ORD-78403", "PICKED_UP", "Picked up from warehouse", "WH-HYD-01 Hyderabad", t(20))
    ev("ORD-78403", "IN_TRANSIT", "Departed Hyderabad hub", "Hyderabad hub", t(8))

    ev("ORD-78404", "PICKED_UP", "Picked up from warehouse", "WH-BOM-01 Mumbai", t(130))
    ev("ORD-78404", "OUT_FOR_DELIVERY", "Out for delivery", "Baner delivery centre", t(100))
    ev("ORD-78404", "DELIVERED", "Delivered to customer", "Pune", t(98))

    ev("ORD-78406", "MANIFESTED", "Shipment label created", "WH-BLR-01 Bengaluru", t(2))

    # S3: weather hold at T-20h, but it only reached us at T-14h (6 hours late)
    ev("ORD-78433", "MANIFESTED", "Shipment label created", "WH-DEL-01 Delhi", t(50))
    ev("ORD-78433", "PICKED_UP", "Picked up from warehouse", "WH-DEL-01 Delhi", t(46))
    ev("ORD-78433", "ARRIVED_AT_HUB", "Arrived at transit hub", "Nagpur hub", t(30))
    ev("ORD-78433", "EXCEPTION", "Held at hub due to heavy rain; line-haul suspended", "Nagpur hub",
       t(20), received_at=t(14), exception="WX-HOLD")

    ev("ORD-78446", "PICKED_UP", "Picked up from warehouse", "WH-BOM-01 Mumbai", t(24))
    ev("ORD-78446", "IN_TRANSIT", "Departed Mumbai hub", "Mumbai hub", t(10))
    ev("ORD-78447", "PICKED_UP", "Picked up from warehouse", "WH-BOM-01 Mumbai", t(18))
    ev("ORD-78447", "IN_TRANSIT", "Departed Mumbai hub", "Mumbai hub", t(6))

    # S9: label created, never picked up, yet the order system says SHIPPED
    ev("ORD-78465", "MANIFESTED", "Shipment label created", "WH-BLR-01 Bengaluru", t(31))

    # S10: nothing after T-96h
    ev("ORD-78468", "PICKED_UP", "Picked up from warehouse", "WH-HYD-01 Hyderabad", t(120))
    ev("ORD-78468", "IN_TRANSIT", "Departed Hyderabad hub", "Hyderabad hub", t(96))

    # -------------------------------------------------------- warehouse events
    warehouse_events = [
        {"event_id": "WHE-1041", "warehouse_id": "WH-BLR-01", "event_type": "POWER_OUTAGE", "severity": "MEDIUM",
         "description": "Grid power cut; generator backup engaged; outbound paused 90 minutes",
         "started_at": ago(h=240), "ended_at": ago(h=238, m=30)},
        {"event_id": "WHE-1046", "warehouse_id": "WH-DEL-01", "event_type": "DOCK_CLOSED", "severity": "LOW",
         "description": "Dock 3 closed for leveller repair; docks 1 and 2 open",
         "started_at": ago(h=144), "ended_at": ago(h=136)},
        {"event_id": "WHE-1050", "warehouse_id": "WH-BOM-01", "event_type": "LABOUR_SHORTAGE", "severity": "LOW",
         "description": "Night shift at 70% strength; picking slowed",
         "started_at": ago(h=96), "ended_at": ago(h=84)},
        # S5: ongoing (no end time)
        {"event_id": "WHE-1053", "warehouse_id": "WH-HYD-01", "event_type": "SYSTEM_DOWN", "severity": "HIGH",
         "description": "WMS outage: pick/pack scanners and wave release unavailable; vendor investigating",
         "started_at": ago(h=3), "ended_at": None},
    ]

    # -------------------------------------------------------------- change log
    change_log = [
        {"change_id": "CHG-2302", "changed_at": ago(h=216), "system": "Inventory sync connector",
         "scope": "WH-BLR-01", "change_type": "UPGRADE",
         "description": "Inventory sync connector upgraded to v5.1; schedule unchanged (every 5 minutes)",
         "changed_by": "integration-platform-team", "ticket": "REL-4398"},
        {"change_id": "CHG-2305", "changed_at": ago(h=72), "system": "Carrier rate card",
         "scope": "carrier:Blue Dart", "change_type": "DATA",
         "description": "Blue Dart surface rate card updated for Q4; no change to service levels",
         "changed_by": "logistics-procurement", "ticket": "REL-4420"},
        {"change_id": "CHG-2307", "changed_at": ago(h=48), "system": "Pricing engine",
         "scope": "ALL", "change_type": "DATA",
         "description": "Festive promotion prices loaded for 120 SKUs",
         "changed_by": "pricing-team", "ticket": "REL-4431"},
        # S6: the cause of ORD-78450..53
        {"change_id": "CHG-2311", "changed_at": ago(h=20), "system": "OMS allocation engine",
         "scope": "WH-BOM-01", "change_type": "CONFIG",
         "description": "Allocation rule set v2 released for WH-BOM-01: zone-based eligibility by delivery pincode replaces the nearest-stock rule",
         "changed_by": "fulfilment-config-team", "ticket": "REL-4471"},
    ]

    return {"orders": orders, "inventory": inventory, "carrier_events": carrier_events,
            "warehouse_events": warehouse_events, "change_log": change_log}


def check(tables: dict[str, list[dict]], T: datetime) -> None:
    """Fail loudly if a planted fact in scenarios.md no longer holds."""
    orders = {o["order_id"]: o for o in tables["orders"]}
    inv = {(r["warehouse_id"], r["sku"]): r for r in tables["inventory"]}
    events: dict[str, list[dict]] = {}
    for e in tables["carrier_events"]:
        events.setdefault(e["order_id"], []).append(e)

    def parse(s: str) -> datetime:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

    def stock_for(order_id: str) -> dict | None:
        o = orders[order_id]
        return inv.get((o["warehouse_id"], o["sku"]))

    for r in tables["inventory"]:
        assert r["available"] == r["on_hand"] - r["reserved"], r
    for e in tables["carrier_events"]:
        assert orders[e["order_id"]]["tracking_number"] == e["tracking_number"], e
    assert "ORD-99999" not in orders

    s = stock_for("ORD-78421")                                   # S1
    assert orders["ORD-78421"]["quantity"] == 40 and s["available"] == 7 and s["on_hand"] < 40
    s = stock_for("ORD-78430")                                   # S2
    assert s["on_hand"] >= orders["ORD-78430"]["quantity"] > s["available"]
    assert s["reserved"] == orders["ORD-78431"]["quantity"]
    hold = [e for e in events["ORD-78433"] if e["exception_code"] == "WX-HOLD"][0]   # S3
    assert parse(hold["received_at"]) - parse(hold["event_at"]) == timedelta(hours=6)
    assert orders["ORD-78436"]["payment_status"] == "CREDIT_HOLD"                    # S4
    assert stock_for("ORD-78436")["available"] >= orders["ORD-78436"]["quantity"]
    outage = [w for w in tables["warehouse_events"] if w["warehouse_id"] == "WH-HYD-01" and not w["ended_at"]]
    assert len(outage) == 1 and stock_for("ORD-78440")["available"] >= 3          # S5
    change = next(c for c in tables["change_log"] if c["change_id"] == "CHG-2311")    # S6
    for oid in ("ORD-78450", "ORD-78451", "ORD-78452", "ORD-78453"):
        assert parse(orders[oid]["placed_at"]) > parse(change["changed_at"])
        assert stock_for(oid)["available"] >= orders[oid]["quantity"]
    for oid in ("ORD-78446", "ORD-78447"):
        assert parse(orders[oid]["placed_at"]) < parse(change["changed_at"])
    assert T - parse(stock_for("ORD-78460")["snapshot_at"]) == timedelta(days=2)       # S7
    assert stock_for("ORD-78462") is None                                              # S8
    assert [e["event_code"] for e in events["ORD-78465"]] == ["MANIFESTED"]           # S9
    assert T - parse(events["ORD-78468"][-1]["event_at"]) == timedelta(hours=96)      # S10
    s = stock_for("ORD-78470")                                                         # S11
    assert T - parse(s["snapshot_at"]) <= timedelta(minutes=15)
    assert s["on_hand"] >= orders["ORD-78470"]["quantity"] > s["available"]
    assert s["reserved"] == orders["ORD-78471"]["quantity"]


def write_outputs(tables: dict[str, list[dict]], T: datetime, as_of_given: bool) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        columns = [c[0] for c in SCHEMAS[name]]
        with open(TABLES_DIR / f"{name}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(columns)
            for row in rows:
                assert set(row) == set(columns), (name, set(row) ^ set(columns))
                w.writerow(["" if row[c] is None else row[c] for c in columns])
        schema = [{"name": n, "type": ty, "mode": mode, "description": d} for n, ty, mode, d in SCHEMAS[name]]
        (SCHEMAS_DIR / f"{name}.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "generated_at": fmt(T),
        "as_of_given": as_of_given,
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "note": "All times are offsets from generated_at (T). See scenarios.md.",
    }
    (TABLES_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--as-of", help="fix T instead of using now, e.g. 2026-11-15T09:00:00Z")
    args = p.parse_args()

    if args.as_of:
        T = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
        if T.tzinfo is None:
            raise SystemExit("--as-of needs a time zone, e.g. 2026-11-15T09:00:00Z")
        T = T.astimezone(timezone.utc)
    else:
        T = datetime.now(timezone.utc)
    T = T.replace(second=0, microsecond=0)

    tables = build_tables(T)
    check(tables, T)
    write_outputs(tables, T, as_of_given=bool(args.as_of))

    print(f"T = {fmt(T)}  (all times in the tables are relative to this)")
    for name, rows in tables.items():
        print(f"  {name:<17} {len(rows):>3} rows  -> {TABLES_DIR.relative_to(DATA_DIR.parent)}/{name}.csv")
    print(f"  schemas -> {SCHEMAS_DIR.relative_to(DATA_DIR.parent)}/  manifest -> tables/manifest.json")


if __name__ == "__main__":
    main()
