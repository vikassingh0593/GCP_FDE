---
doc_id: RB-PAY-004
title: Payment hold
doc_type: runbook
exception_type: payment_hold
version: 2
status: current
effective_date: 2026-03-10
owner: Payments Risk
---

# Payment hold (RB-PAY-004 v2)

## Symptoms
- The order is ON_HOLD and its payment status is CREDIT_HOLD.
- Reason codes:
  - PAY-H201: credit hold. The order value is above the customer's credit or cash-on-delivery limit.
  - PAY-H205: fraud review. The risk engine flagged the order for manual review.
  - PAY-H210: the payment authorisation expired before capture.

## Checks
1. Read the order's payment status, reason code and the time it went on hold.
2. Confirm that stock is available at the assigned warehouse, so the analyst knows the order can ship once payment clears. Available stock does not change the hold.
3. Work out how long the order has been on hold. A hold over 24 hours breaches the payments service level.
4. Do not guess why the risk engine placed the hold beyond what the reason code says. The decision data belongs to Payments Risk.

## Escalation
- Only Payments Risk can release a hold. The control tower never releases or overrides a payment hold.
- Holds older than 24 hours: escalate to the Payments Risk queue with the order ID and reason code.
- Customer messages say "payment verification in progress". Never share limits, scores or risk reasons with the customer.
