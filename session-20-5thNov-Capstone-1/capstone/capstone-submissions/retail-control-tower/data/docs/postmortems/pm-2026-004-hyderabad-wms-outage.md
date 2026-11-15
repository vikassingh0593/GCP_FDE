---
doc_id: PM-2026-004
title: Hyderabad WMS outage stopped picking for five hours
doc_type: postmortem
incident_date: 2026-01-27
warehouse_id: WH-HYD-01
carrier: none
region: South
exception_type: warehouse_disruption
root_cause_category: system_outage
severity: SEV-2
duration_hours: 5
---

# PM-2026-004: Hyderabad WMS outage stopped picking for five hours

## Summary
The warehouse management system (WMS) at WH-HYD-01 was down for 5 hours after a failed database failover. Picking and packing stopped, and 320 orders were stuck in PICKING. The stock ledger was not affected, so inventory numbers stayed correct. Orders that carriers had already picked up were not affected.

## Timeline
All times IST.
- 11:10 The WMS database primary fails; the automatic failover points to a replica under maintenance.
- 11:15 Pick/pack scanners lose connection. Wave release stops.
- 11:40 Warehouse Operations opens a SYSTEM_DOWN warehouse event.
- 14:30 The vendor restores the primary database.
- 16:10 Scanners reconnect and the picking backlog starts to clear.

## Root cause
The failover script had a hard-coded replica address. That replica was under planned maintenance, so the failover connected to a database that refused writes.

## Fix
- The failover script now discovers healthy replicas instead of using a fixed address.
- Failover is tested every month.
- A warehouse event is raised automatically when scanners lose connection for more than 10 minutes.

## Lessons
- An open SYSTEM_DOWN event explains orders stuck in PICKING at that warehouse.
- The stock ledger stays correct during a WMS outage: stock can be available while the warehouse cannot ship.
- Get the recovery time from Warehouse Operations; do not estimate it.
- Re-routing affected orders needs Fulfilment duty manager approval.
