---
doc_id: RB-WH-005
title: Warehouse disruption
doc_type: runbook
exception_type: warehouse_disruption
version: 3
status: current
effective_date: 2026-05-20
owner: Warehouse Operations
---

# Warehouse disruption (RB-WH-005 v3)

## Symptoms
- Orders at one warehouse stop moving through PICKING or PACKED.
- A warehouse event is open (it has no end time) at that warehouse.

## Warehouse event types
- SYSTEM_DOWN: the warehouse management system (WMS) or its scanners are unavailable; picking and packing stop.
- DOCK_CLOSED: one or more loading docks are closed; outbound slows or stops.
- POWER_OUTAGE: grid power is lost; work pauses until backup power is stable.
- LABOUR_SHORTAGE: a shift is understaffed; picking slows.

## Checks
1. List the warehouse events at the order's assigned warehouse. An event is ongoing when it has no end time.
2. Check that the event overlaps the order's current stage. An order the carrier picked up before the event started is not affected by it.
3. Check the inventory record. It comes from the stock ledger, not the WMS, so it stays current during a WMS outage. Stock can be available even though the warehouse cannot ship.
4. Count the other open orders at the same warehouse in PICKING or PACKED; they are probably affected too.
5. Ask Warehouse Operations for the expected recovery time. Never estimate it.

## Escalation
- SYSTEM_DOWN for more than 2 hours: Warehouse Operations raises a SEV-2 incident.
- Re-routing affected orders to another warehouse needs Fulfilment duty manager approval.
