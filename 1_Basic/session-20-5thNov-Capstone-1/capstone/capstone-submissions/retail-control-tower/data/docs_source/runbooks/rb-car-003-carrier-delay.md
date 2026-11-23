---
doc_id: RB-CAR-003
title: Carrier delay
doc_type: runbook
exception_type: carrier_delay
version: 4
status: current
effective_date: 2026-02-15
owner: Logistics Operations
---

# Carrier delay (RB-CAR-003 v4)

## Symptoms
- The order is SHIPPED, but the promised delivery time has passed or will be missed.
- The latest carrier event is an EXCEPTION, or no new carrier event has arrived for a long time.

## Carrier exception codes
- WX-HOLD: shipment held at a hub because of weather. Usually clears in 24 to 72 hours.
- HUB-CONG: hub congestion; shipments wait for the next line-haul.
- ADDR-INC: address incomplete or wrong; the carrier needs the customer to confirm it.
- NO-PICKUP: the carrier did not collect the shipment from the warehouse.
- RTO-INIT: return to origin started; the shipment is coming back.

## Checks
1. Read all carrier events for the order in event-time order. Note the latest event, its code, location and time.
2. Compare the event time with the received time. Carrier feeds can deliver events hours late, so the latest event you can see may not be the latest that happened. Report any lag over 2 hours.
3. If the latest event is an EXCEPTION, its exception code is the carrier's stated cause.
4. If the order is SHIPPED but there is no PICKED_UP event, the order record and the carrier disagree. Do not pick one side. Treat it as a conflict: ask the warehouse for the handover scan and the carrier for pickup confirmation.
5. If a shipment in transit has had no event for more than 48 hours, the cause is unknown. Raise a trace request with the carrier.

## Escalation
- WX-HOLD and HUB-CONG: tell Customer Care the hub name and the carrier's expected release time. Do not re-ship while the shipment is held.
- NO-PICKUP, or a shipped-without-pickup conflict: Logistics Operations contacts the carrier's account team within 4 hours.
- No events for more than 72 hours: open a lost-shipment investigation with the carrier. A re-ship needs Logistics Operations approval.
