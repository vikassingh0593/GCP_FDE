---
doc_id: PM-2026-021
title: Delayed Delhivery tracking feed made shipped orders look lost
doc_type: postmortem
incident_date: 2026-06-30
warehouse_id: WH-BLR-01
carrier: Delhivery
region: South
exception_type: carrier_delay
root_cause_category: carrier_integration
severity: SEV-3
duration_hours: 10
---

# PM-2026-021: Delayed Delhivery tracking feed made shipped orders look lost

## Summary
For 10 hours, orders handed to Delhivery at WH-BLR-01 showed SHIPPED in the order system but had no PICKED_UP carrier event. Most had been picked up and the carrier's event feed was simply late. But 14 shipments had really been missed at pickup and were still on the dock.

## Timeline
All times IST.
- 18:00 Delhivery's batch export of tracking events stalls.
- 21:00 Orders shipped since 18:00 show no pickup event.
- 07:30 next day: Customer Care asks why tracking shows "label created" only.
- 08:00 Delhivery confirms the feed delay; the backlog of events arrives by 09:00.
- 09:30 A dock check finds 14 parcels that were never collected; they are picked up at 11:00.

## Root cause
Two separate problems looked the same in our data. Delhivery's batch export job stalled, which delayed events for every shipment. On the same evening, one pickup van skipped a dock, so 14 shipments were never collected.

## Fix
- An hourly feed-lag alert now compares the newest carrier event time with the current time.
- A pickup report from the carrier is checked against our handover list every evening.

## Lessons
- SHIPPED without a PICKED_UP event is a conflict, not proof either way.
- A late feed and a missed pickup look identical in the data. Confirm with the warehouse handover scan and with the carrier.
- Do not tell the customer the parcel is on its way until the pickup is confirmed.
