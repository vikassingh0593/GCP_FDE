---
doc_id: RB-CHG-006
title: Change-related incident
doc_type: runbook
exception_type: recent_change
version: 1
status: current
effective_date: 2026-06-01
owner: Fulfilment Operations
---

# Change-related incident (RB-CHG-006 v1)

## Symptoms
- Several orders at one warehouse, carrier or region fail in the same way, starting at about the same time.
- A reason code that was rare before starts appearing in a cluster, for example ALLOC-E107.
- Stock, carrier and warehouse checks do not explain the failures.

## Checks
1. Find when the cluster started: the time of the earliest affected order.
2. Read the change log for the same scope (warehouse, carrier or system) from 48 hours before that time.
3. Compare orders placed before and after the change. If orders before it were processed normally and orders after it fail, the change is the likely cause. If both fail, look elsewhere.
4. Rule out the other causes for the affected orders: stock is available, no warehouse event is open, and there is no carrier exception.
5. Report the change ID, its time, its owner and the before/after evidence. A change that only happened close in time, without the before/after pattern, is not evidence.

## Escalation
- The rollback decision belongs to the change owner named in the change log. The control tower recommends a rollback; it never performs one.
- Five or more affected orders: raise a SEV-2 incident with the change owner.
