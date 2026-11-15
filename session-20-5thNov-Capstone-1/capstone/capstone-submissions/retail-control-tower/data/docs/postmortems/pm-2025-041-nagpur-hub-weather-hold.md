---
doc_id: PM-2025-041
title: Nagpur hub weather hold delayed Blue Dart shipments
doc_type: postmortem
incident_date: 2025-08-14
warehouse_id: none
carrier: Blue Dart
region: Central
exception_type: carrier_delay
root_cause_category: carrier_disruption
severity: SEV-3
duration_hours: 52
---

# PM-2025-041: Nagpur hub weather hold delayed Blue Dart shipments

## Summary
Heavy rain flooded the roads around the Blue Dart hub in Nagpur. About 1,200 shipments, 180 of them ours, were held with exception code WX-HOLD for up to 52 hours. Several hold events reached us 5 to 7 hours after they happened, because the hub's network link was down.

## Timeline
All times IST.
- Day 1, 03:00 The hub stops outbound line-haul.
- Day 1, 09:00 The first WX-HOLD events arrive, with event times between 03:00 and 04:00.
- Day 1, 12:00 Customer Care is told and starts proactive messages.
- Day 2, 18:00 Partial release; line-haul restarts on one route.
- Day 3, 07:00 All held shipments are moving again.

## Root cause
Weather. Hub operations stopped line-haul for safety. There was no fault on our side or the carrier's.

## Fix
- A proactive customer message now goes out for every WX-HOLD shipment.
- Blue Dart sends a daily hold report during the monsoon.

## Lessons
- In this incident, WX-HOLD cleared within 24 to 72 hours. Do not re-ship during a hold.
- Hold events can arrive hours late. Compare each event's time with the time it was received.
- A past hold at the same hub is not evidence of a current one. Confirm it from the shipment's own carrier events.
