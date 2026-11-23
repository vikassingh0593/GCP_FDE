---
doc_id: RB-ALLOC-002
title: Allocation failure
doc_type: runbook
exception_type: allocation
version: 3
status: current
effective_date: 2026-07-01
supersedes: RB-ALLOC-002 v2
owner: Fulfilment Operations
---

# Allocation failure (RB-ALLOC-002 v3)

## Symptoms
- The order stays in ALLOCATION_PENDING after the normal allocation cycle (about 15 minutes).
- Reason code ALLOC-E101: the available quantity is below the ordered quantity. Stock may be on hand but held (reserved) for other orders.
- Reason code ALLOC-E107: no eligible warehouse under the current allocation rules, even though stock exists.

## Checks for ALLOC-E101
1. Read the current inventory record for the assigned warehouse and SKU, including the snapshot time. If the snapshot is older than the allowed age, the quantities are not current evidence: report them as unconfirmed.
2. If on hand is below the ordered quantity, this is a shortage: follow RB-INV-001.
3. If on hand is enough but available is not, the stock is reserved. Find the orders holding the reservation: allocated orders for the same SKU at the same warehouse. Bulk B2B orders and promotion pre-allocations are the usual holders.
4. Check that the reservation is legitimate. An allocated order with a valid promise date is legitimate, even when it is large.
5. Check available stock of the same SKU at the other warehouses, for a re-route recommendation.

## Checks for ALLOC-E107
1. Count recent orders at the same warehouse with ALLOC-E107. One order points to an order-level problem, such as an address outside every delivery zone. Many orders point to a rule problem.
2. Confirm that stock is available for the affected SKUs. If it is, the problem is eligibility, not stock.
3. Check the change log for allocation rule releases at that warehouse before the first affected order, and follow RB-CHG-006.

## Escalation
- The control tower never releases reserved stock. Only the Fulfilment duty manager can release a reservation, and a B2B contract reservation also needs the account manager's approval.
- Rule problems go to the owner of the allocation rule change named in the change log.
- Re-routing needs approval from the Fulfilment duty manager.
