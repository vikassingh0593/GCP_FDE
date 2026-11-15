---
doc_id: RB-INV-001
title: Inventory shortage at the assigned warehouse
doc_type: runbook
exception_type: inventory_shortage
version: 2
status: current
effective_date: 2026-04-01
owner: Inventory Control
---

# Inventory shortage at the assigned warehouse (RB-INV-001 v2)

## Symptoms
- The order stays in ALLOCATION_PENDING with reason code ALLOC-E101: the available quantity at the assigned warehouse is below the ordered quantity.
- ALLOC-E101 only says that available stock is too low. It does not say why. A true shortage, stock held by other orders and an out-of-date inventory snapshot all produce the same code.
- Large orders (B2B, catering, events) hit this more often, because one order can exceed a warehouse's whole stock of a SKU.

## Checks
1. Read the current inventory record for the assigned warehouse and SKU: on hand, reserved, available and snapshot time.
2. Check the snapshot age first. If the snapshot is older than the allowed age, the quantities are not current evidence. Stop, report the inventory as unconfirmed, and ask Inventory Control to refresh the snapshot.
3. Compare on hand with the ordered quantity.
   - On hand is below the ordered quantity: this is a true shortage. Continue with step 4.
   - On hand is enough, but reserved stock leaves too little available: this is an allocation problem, not a shortage. Follow RB-ALLOC-002.
4. Record the shortfall: ordered quantity minus available quantity at the assigned warehouse.
5. Check available stock of the same SKU at the other warehouses, and list each one that could fulfil the full quantity.
6. Replenishment dates are held by Inventory Control and are not in the control tower data. Ask; never estimate one.

## Escalation
- Re-routing an order to another warehouse needs approval from the Fulfilment duty manager. The control tower recommends a re-route; it never moves the order.
- A shortfall on a B2B order: tell the account manager the same day.
- More than 20 orders short on one SKU at one warehouse: raise a stock incident with Inventory Control.
