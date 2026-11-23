---
doc_id: PM-2026-017
title: Mumbai allocation rule release made in-stock orders ineligible
doc_type: postmortem
incident_date: 2026-05-22
warehouse_id: WH-BOM-01
carrier: none
region: West
exception_type: recent_change
root_cause_category: config_change
severity: SEV-2
duration_hours: 6
---

# PM-2026-017: Mumbai allocation rule release made in-stock orders ineligible

## Summary
After an allocation rule update at WH-BOM-01, 210 orders failed allocation with ALLOC-E107 for 6 hours, although the warehouse had stock for all of them. Orders placed before the release were not affected.

## Timeline
All times IST.
- 14:00 An allocation rule update is released for WH-BOM-01 (the delivery zone table changed).
- 14:20 The first ALLOC-E107 failures appear.
- 17:30 Customer Care escalates a cluster of unconfirmed Mumbai orders.
- 18:45 An analyst compares orders placed before and after 14:00: every failure is after the release.
- 19:30 The change owner rolls back the rule update.
- 20:00 Allocation is re-run and the backlog clears.

## Root cause
The new rule matched delivery pincodes against a zone table that was missing about a third of Mumbai's pincodes. Orders to those pincodes had no eligible warehouse. The release had no regression test on the zone table.

## Fix
- The rule update was rolled back and the old zone table restored.
- Allocation rule releases now need a dry run against the previous day's orders.

## Lessons
- A cluster of ALLOC-E107 at one warehouse, with stock available, points to the allocation rules. Check the change log first.
- Compare orders placed before and after the release. That comparison, not the timing alone, is what shows the change caused the failures.
- The rollback decision belongs to the change owner.
