---
doc_id: PM-2025-052
title: Risk rule update put repeat customers on credit hold
doc_type: postmortem
incident_date: 2025-10-09
warehouse_id: none
carrier: none
region: National
exception_type: payment_hold
root_cause_category: payment_risk
severity: SEV-3
duration_hours: 14
---

# PM-2025-052: Risk rule update put repeat customers on credit hold

## Summary
A risk rule update treated repeat cash-on-delivery customers as new customers. For 14 hours, about 300 orders across all regions went to CREDIT_HOLD with reason code PAY-H201.

## Timeline
All times IST.
- 08:00 The risk rule update is released.
- 10:30 The CREDIT_HOLD count is three times its normal level.
- 15:00 Payments Risk finds that the customer-tenure field is empty for migrated accounts.
- 18:00 The rule is reverted.
- 22:00 Payments Risk finishes releasing the held orders in batches.

## Root cause
A data migration had left the customer-tenure field empty for older accounts. The new rule read an empty tenure as "new customer" and applied the lower credit limit.

## Fix
- The rule was reverted, and the tenure field was backfilled.
- Risk rule releases now include a check on how many orders the rule would have held the day before.

## Lessons
- A spike of PAY-H201 across many regions points to the risk rules. A single PAY-H201 hold is normal business and is not evidence of a rule fault.
- Only Payments Risk can release a hold.
