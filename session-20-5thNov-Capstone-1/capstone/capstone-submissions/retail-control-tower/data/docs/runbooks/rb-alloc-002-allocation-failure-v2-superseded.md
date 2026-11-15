---
doc_id: RB-ALLOC-002
title: Allocation failure
doc_type: runbook
exception_type: allocation
version: 2
status: superseded
effective_date: 2025-09-01
superseded_by: RB-ALLOC-002 v3
superseded_date: 2026-07-01
owner: Fulfilment Operations
---

# Allocation failure (RB-ALLOC-002 v2, superseded)

## Symptoms
- The order stays in ALLOCATION_PENDING with reason code ALLOC-E101 or ALLOC-E107.

## Checks
1. Open the legacy allocation dashboard (ALLOCX) and search for the order.
2. If the reason code is ALLOC-E101 and the reservations on the SKU are older than 24 hours, ask the warehouse lead to release them and re-run allocation.
3. For ALLOC-E107, re-run allocation manually from ALLOCX. If it fails twice, raise a ticket with the OMS team.

## Escalation
- The warehouse lead can release reservations older than 24 hours without further approval.
- Unresolved after 4 hours: escalate to the OMS on-call engineer.
