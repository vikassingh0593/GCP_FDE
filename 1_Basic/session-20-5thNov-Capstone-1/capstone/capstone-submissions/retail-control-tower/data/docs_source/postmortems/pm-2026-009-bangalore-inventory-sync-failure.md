---
doc_id: PM-2026-009
title: Bangalore inventory sync failure left orders stuck in allocation
doc_type: postmortem
incident_date: 2026-03-18
warehouse_id: WH-BLR-01
carrier: none
region: South
exception_type: allocation
root_cause_category: inventory_sync
severity: SEV-2
duration_hours: 9
---

# PM-2026-009: Bangalore inventory sync failure left orders stuck in allocation

## Summary
For about 9 hours, 140 orders at WH-BLR-01 stayed in ALLOCATION_PENDING with reason code ALLOC-E101. The warehouse had the stock on its shelves, but the inventory record showed almost nothing available. The inventory sync job had stopped, so the record was 9 hours old.

## Timeline
All times IST.
- 01:50 The inventory sync job for WH-BLR-01 fails. No alert fires.
- 06:30 The first orders of the day fail allocation with ALLOC-E101.
- 09:15 Customer Care reports a spike in "order not confirmed" complaints from Bengaluru.
- 10:05 On-call finds that the WH-BLR-01 inventory snapshot is 8 hours old.
- 10:40 The sync job is restarted and the snapshot is current again.
- 11:00 Allocation is re-run and the 140 orders are allocated. Incident closed.

## Root cause
The TLS certificate used by the sync connector expired at 01:50. Every run after that failed, but the job reported success because a retry wrapper swallowed the error. Allocation kept using the last good snapshot, which was taken before the morning stock arrival.

## Fix
- The certificate was renewed and moved to automatic rotation.
- The sync job now fails loudly instead of retrying silently.
- An alert now fires when any warehouse's inventory snapshot is older than 30 minutes.

## Lessons
- Check the inventory snapshot time before trusting the available quantity. A stale snapshot can make a full warehouse look empty.
- ALLOC-E101 on its own does not prove a shortage.
- Re-run allocation only after the snapshot is current again.
