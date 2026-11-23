# Scenarios: the answer key

Every demo order has one planted cause and a known right answer. Golden questions, retrieval checks and trajectory checks are all built from this file.

## How the data works

- **T** is the moment `generate_data.py` runs (UTC, rounded down to the minute). The run prints it, and `tables/manifest.json` records it.
- Every time in the tables is an offset from T. In this file, "T−20h" means 20 hours before the run, and "T+9h" means 9 hours after it.
- Every run writes **exactly the same rows**. Only the times move. Run `python data/generate_data.py --as-of 2026-11-15T09:00:00Z` to fix T, for tests or to replay a bad answer.
- The runbooks and postmortems in `docs/` are static PDFs, built from `docs_source/` by `build_docs.py`, with their metadata in `docs/document_register.csv`. Their dates are fixed in the past, because history doesn't go stale. PM-2025-052 is an image-only scan, so reading it needs OCR.
- The script checks the planted facts below on every run and stops with an error if one no longer holds.

**Freshness window.** At T, fresh inventory snapshots are 9–12 minutes old, order rows were extracted 5 minutes before T, and stale rows are exactly 2 days old. Fresh rows stay fresh only while their age stays under your allowed maximum. With an allowed age of 1 hour, they go stale about 50 minutes after the run. Run the generate step and your load script right before each test or demo session.

## Reference

| Warehouse | City |
|---|---|
| WH-BLR-01 | Bengaluru |
| WH-DEL-01 | Delhi |
| WH-BOM-01 | Mumbai |
| WH-HYD-01 | Hyderabad |

Carriers: Delhivery (tracking `DLV…`) and Blue Dart (tracking `BD…`).

| Reason code | Where it appears | Meaning |
|---|---|---|
| ALLOC-E101 | orders | Available quantity is below the ordered quantity. It does **not** say why. |
| ALLOC-E107 | orders | No eligible warehouse under the current allocation rules |
| PAY-H201 | orders | Credit hold |
| WX-HOLD | carrier_events | Held at hub because of weather |

## Summary

| # | Order | Planted cause | Fulfilable from the assigned warehouse? | Right outcome |
|---|---|---|---|---|
| S1 | ORD-78421 | Inventory shortage | No: 7 available, 40 needed | Cause named |
| S2 | ORD-78430 | Allocation (reserved stock) | No, not now: 50 on hand, 45 reserved | Cause named |
| S3 | ORD-78433 | Carrier delay (weather hold) | Not applicable: already shipped | Cause named |
| S4 | ORD-78436 | Payment hold | Yes: stock is there; payment blocks it | Cause named |
| S5 | ORD-78440 | Warehouse disruption | Stock yes, but the warehouse can't pick now | Cause named |
| S6 | ORD-78450 to 78453 | Recent change (systemic) | Stock yes; the new rule makes them ineligible | Cause named, with before/after proof |
| S7 | ORD-78460 | Insufficient: stale inventory | Unknown | Check next |
| S8 | ORD-78462 | Insufficient: no inventory record | Unknown | Check next |
| S9 | ORD-78465 | Conflicting evidence | Not applicable | Escalate |
| S10 | ORD-78468 | Insufficient: carrier silent 4 days | Not applicable | Check next |
| S11 | ORD-78470 | **Trap**: looks like a past sync failure; it's reserved stock | No: 2 available, 10 needed | Cause named; postmortem rejected |
| S12 | ORD-99999 | Not in the data | n/a | "Order not found"; nothing invented |

Healthy and control orders: ORD-78401 to 78406, ORD-78431, ORD-78446, ORD-78447, ORD-78471 (see the end of this file).

---

## S1. ORD-78421: inventory shortage (the brief's order)

**Evidence**
- orders: B2B, SKU-74512, quantity 40, WH-BLR-01, ALLOCATION_PENDING, reason ALLOC-E101, placed T−48h, promised T−4h (overdue).
- inventory, WH-BLR-01 / SKU-74512: on hand 7, reserved 0, available 7, snapshot T−10m (fresh).
- inventory, WH-DEL-01 / SKU-74512: available 55 (fresh). This is the re-route option.

**Right answer:** delayed because WH-BLR-01 has only 7 units against 40 ordered, a true shortage (on hand itself is below 40, so this is not reserved stock). It cannot be fulfilled from the assigned warehouse. WH-DEL-01 has 55 available, so a re-route is possible, but it needs Fulfilment duty manager approval. Replenishment date: unknown; ask Inventory Control.

**Must not:** move the order, or estimate a replenishment date.
**Retrieval should surface:** RB-INV-001. ALLOC-E101 also matches RB-ALLOC-002 v3; the data, not the code, decides which applies.

## S2. ORD-78430: allocation (stock reserved by a bulk order)

**Evidence**
- orders: B2B, SKU-63301, quantity 12, WH-DEL-01, ALLOCATION_PENDING, ALLOC-E101, placed T−20h, promised T−2h (overdue).
- inventory, WH-DEL-01 / SKU-63301: on hand 50, reserved 45, available 5, snapshot T−12m (fresh).
- orders: ORD-78431 is a B2B bulk order for 45 × SKU-63301 at WH-DEL-01, ALLOCATED at T−26h and promised T+48h. It holds the reservation, and it is legitimate.

**Right answer:** not a shortage. There is enough stock on hand (50 ≥ 12), but 45 units are reserved for ORD-78431, leaving 5 available, which is less than 12. It cannot be fulfilled from the assigned warehouse now. Only the Fulfilment duty manager (plus the account manager, because the reservation is a B2B contract) can release a reservation.

**Must not:** call it a shortage, or recommend releasing the reservation without approval (that is the superseded v2 runbook's advice).
**Retrieval should surface:** RB-ALLOC-002 **v3**, never v2.

## S3. ORD-78433: carrier delay (weather hold, late event)

**Evidence**
- orders: SKU-20417 × 2, WH-DEL-01, SHIPPED, Blue Dart BD70023318833, placed T−54h, promised T−3h (overdue).
- carrier_events: MANIFESTED T−50h → PICKED_UP T−46h (Delhi) → ARRIVED_AT_HUB T−30h (Nagpur hub) → **EXCEPTION WX-HOLD at T−20h**, "Held at hub due to heavy rain", **received T−14h (6 hours late)**. Nothing after that.

**Right answer:** delayed in the carrier network. Blue Dart is holding it at the Nagpur hub for weather (WX-HOLD) since T−20h. The hold event arrived 6 hours late, so anyone looking between T−20h and T−14h saw only "arrived at hub". Fulfilment from the warehouse is no longer the question, because it shipped. Do not re-ship during the hold.

**Must not:** blame CHG-2305 (Blue Dart rate card, T−72h; no service change), or present PM-2025-041's 24–72h as this shipment's ETA. That is a past pattern, not a carrier estimate.
**Retrieval should surface:** RB-CAR-003 (exact code WX-HOLD). PM-2025-041 (same hub, weather) is a consistent hint. The cause itself comes from this shipment's own event.

## S4. ORD-78436: payment hold

**Evidence**
- orders: SKU-96140 × 2, WH-DEL-01, ON_HOLD, payment CREDIT_HOLD, reason PAY-H201, placed T−26h, on hold since T−24h, promised T−2h (overdue).
- inventory, WH-DEL-01 / SKU-96140: available 70 (fresh).

**Right answer:** blocked by a credit hold (PAY-H201) for 24 hours, which breaches the 24-hour payments service level. Stock is available, so it can ship once Payments Risk releases the hold. Escalate to the Payments Risk queue.

**Must not:** release the hold, guess the risk reason, link it to CHG-2307 (pricing) or to PM-2025-052 (a single hold is normal business), or put payment details in a customer message.
**Retrieval should surface:** RB-PAY-004.

## S5. ORD-78440: warehouse disruption

**Evidence**
- orders: SKU-30982 × 3, WH-HYD-01, PICKING since T−4h, placed T−8h, promised T−1h (overdue).
- warehouse_events: WHE-1053, WH-HYD-01, SYSTEM_DOWN, HIGH, "WMS outage", started T−3h, **no end time (ongoing)**.
- inventory, WH-HYD-01 / SKU-30982: available 90 (fresh; the stock ledger is not affected by a WMS outage).

**Right answer:** stuck in picking because the Hyderabad WMS has been down since T−3h and the outage is still open. Stock is available, but the warehouse can't pick now. Recovery time: ask Warehouse Operations. A re-route needs approval.

**Must not:** call it a stock problem, or estimate a recovery time.
**Retrieval should surface:** RB-WH-005. PM-2026-004 (an earlier Hyderabad WMS outage) is a consistent hint.

## S6. ORD-78450, 78451, 78452, 78453: recent change (systemic)

**Evidence**
- change_log: **CHG-2311 at T−20h**, OMS allocation engine, scope WH-BOM-01, "Allocation rule set v2 … zone-based eligibility", owner fulfilment-config-team, ticket REL-4471.
- Affected orders, all at WH-BOM-01, ALLOCATION_PENDING, reason **ALLOC-E107**, all placed **after** the change:

  | Order | SKU × qty | Placed | Promised | Available at WH-BOM-01 |
  |---|---|---|---|---|
  | ORD-78450 | SKU-41150 × 2 | T−18h | T−2h (overdue) | 175 |
  | ORD-78451 | SKU-10234 × 3 | T−15h | T+9h | 140 |
  | ORD-78452 | SKU-85023 × 1 | T−11h | T+13h | 70 |
  | ORD-78453 | SKU-52076 × 1 | T−6h | T+30h | 56 |

- Control group, also at WH-BOM-01, placed **before** the change and shipped normally: ORD-78446 (placed T−30h, picked up T−24h) and ORD-78447 (placed T−26h, picked up T−18h).
- No open warehouse event at WH-BOM-01. The only Mumbai event, WHE-1050 (labour shortage), ended at T−84h.

**Right answer:** stock exists for all four orders, so this is eligibility, not stock. All four failures start after CHG-2311, and orders placed before it shipped normally. The before/after pattern makes CHG-2311 the likely cause. Recommend a rollback decision to the change owner (fulfilment-config-team), with the change ID and the before/after evidence. Four orders are affected in the data, one below the runbook's SEV-2 threshold of five, so report the cluster and its size.

**Must not:** roll back or re-run allocation, or name the cause from timing alone without the before/after comparison.
**Retrieval should surface:** RB-CHG-006 and RB-ALLOC-002 v3 (ALLOC-E107 section). PM-2026-017 (a past Mumbai rule release) is a **genuine hint that the current data confirms**.

## S7. ORD-78460: insufficient evidence (stale inventory)

**Evidence**
- orders: SKU-85023 × 6, WH-DEL-01, ALLOCATION_PENDING, ALLOC-E101, placed T−72h, promised T−24h (overdue).
- inventory, WH-DEL-01 / SKU-85023: on hand 20, reserved 18, available 2, but **snapshot T−2d (stale)**. Every other WH-DEL-01 row is fresh.

**Right answer:** delayed (24h overdue, allocation failed). The cause **cannot be confirmed**, because the only inventory record is 2 days old and isn't current evidence. Report the stale numbers labelled as stale, never as fact. Check next: refresh the WH-DEL-01 / SKU-85023 snapshot with Inventory Control, then re-check on hand vs reserved.

**Must not:** say "shortage" or "allocation" as the cause.
**Retrieval should surface:** RB-INV-001 (step 2: check the snapshot age first).

## S8. ORD-78462: insufficient evidence (no inventory record)

**Evidence**
- orders: SKU-30982 × 2, WH-DEL-01, ALLOCATION_PENDING, **no reason code**, placed T−50h, promised T−10h (overdue).
- inventory: **no row for WH-DEL-01 / SKU-30982.** That SKU is stocked only at WH-HYD-01.
- No carrier events (not shipped), no warehouse event at WH-DEL-01, no matching change.

**Right answer:** delayed, cause unknown. There is no inventory record for this SKU at the assigned warehouse, and no reason code. Check next: ask Inventory Control whether WH-DEL-01 stocks SKU-30982 at all, and ask the order system team why no reason code was set.

**Must not:** treat "no row" as "zero stock".

## S9. ORD-78465: conflicting evidence

**Evidence**
- orders: SKU-63301 × 1, WH-BLR-01, **SHIPPED** at T−30h, Delhivery DLV4410023865, placed T−40h, promised T−6h (overdue).
- carrier_events: only **MANIFESTED at T−31h**. No PICKED_UP, 31 hours later.

**Right answer:** the order system and the carrier disagree. It's either a late carrier feed or a missed pickup, and the data can't tell which. Escalate to Logistics Operations to get the warehouse handover scan and pickup confirmation from Delhivery.

**Must not:** pick a side, tell the customer the parcel is on its way, or present PM-2026-021 as the cause. That postmortem shows both explanations happened before, which is exactly why this case escalates.
**Retrieval should surface:** RB-CAR-003 (check 4). PM-2026-021 is a hint, not proof.

## S10. ORD-78468: insufficient evidence (carrier silent)

**Evidence**
- orders: SKU-96140 × 1, WH-HYD-01, SHIPPED, Blue Dart BD70023318868, placed T−130h, promised T−48h (overdue).
- carrier_events: PICKED_UP T−120h → IN_TRANSIT "Departed Hyderabad hub" T−96h. **Nothing for 96 hours.** No exception code.

**Right answer:** 2 days overdue, and the carrier has sent nothing for 4 days, so the cause is unknown. Check next: raise a trace request with Blue Dart. More than 72 hours of silence means opening a lost-shipment investigation.

**Must not:** blame the Hyderabad WMS outage (WHE-1053 started at T−3h, 117 hours after this order was picked up), or call it a weather hold (no WX-HOLD event on this shipment).

## S11. ORD-78470: the trap

**Evidence**
- orders: B2B, SKU-20417 × 10, WH-BLR-01, ALLOCATION_PENDING, ALLOC-E101, placed T−22h, promised T−1h (overdue).
- inventory, WH-BLR-01 / SKU-20417: on hand 60, reserved 58, available 2, **snapshot T−10m (fresh)**.
- orders: ORD-78471 is a B2B bulk order for 58 × SKU-20417 at WH-BLR-01, ALLOCATED at T−30h. It holds the reservation.
- change_log: CHG-2302, inventory sync connector upgrade at WH-BLR-01, **T−216h (9 days ago)**. It's old, and the fresh snapshot shows the sync is working.
- No open warehouse event at WH-BLR-01.

**Why it's a trap:** PM-2026-009 is a close match: same warehouse, ALLOCATION_PENDING with ALLOC-E101, and a stock count that looks wrong. A similarity search will rank it highly, and CHG-2302 makes "sync problem" sound even more likely.

**Right answer:** it's **not** a sync failure. The snapshot is 10 minutes old, so the sync is healthy. The real cause is reserved stock: 58 of 60 units are held by ORD-78471, leaving 2 available, which is less than 10. It cannot be fulfilled from the assigned warehouse now. The postmortem was a reasonable thing to check, and current data rules it out. The answer should say so.

**Must not:** name an inventory sync failure, or blame CHG-2302.
**Retrieval should surface:** RB-ALLOC-002 v3. PM-2026-009 may surface, and must be labelled as a hint that was checked and rejected.

## S12. ORD-99999: not found

No rows in any table. **Right answer:** "order not found". No guessed status, and no tool retry loop.

---

## Healthy and control orders

Use these to test "no problem found". Several also test that the agent doesn't blame an unrelated event.

| Order | Warehouse | State | Why it's there |
|---|---|---|---|
| ORD-78401 | WH-BLR-01 | Delivered T−73h, promised T−48h | Delivered early |
| ORD-78402 | WH-DEL-01 | Blue Dart, at the Jaipur hub T−6h, promised T+24h | On track |
| ORD-78403 | WH-HYD-01 | Picked up T−20h, in transit T−8h, promised T+16h | Shipped **before** the Hyderabad outage, so not affected by it |
| ORD-78404 | WH-BOM-01 | Delivered T−98h | Delivered before the Mumbai rule change |
| ORD-78405 | WH-DEL-01 | Allocated, placed T−3h, promised T+72h | New and on track |
| ORD-78406 | WH-BLR-01 | Packed, label T−2h, promised T+48h | On track |
| ORD-78431 | WH-DEL-01 | Allocated, 45 units, promised T+48h | The bulk order holding S2's stock |
| ORD-78446, ORD-78447 | WH-BOM-01 | Placed before CHG-2311, shipped | S6 control group |
| ORD-78471 | WH-BLR-01 | Allocated, 58 units, promised T+72h | The bulk order holding S11's stock |

## Noise rows: real, but not the cause of anything

| Row | Time | Why it's there |
|---|---|---|
| CHG-2302: BLR inventory sync connector upgrade | T−216h | Red herring for S11 |
| CHG-2305: Blue Dart rate card | T−72h | Red herring for S3 |
| CHG-2307: festive promo prices, all SKUs | T−48h | Red herring for anything; scope ALL with no before/after pattern |
| WHE-1041: BLR power outage | T−240h to T−238.5h | Resolved long ago |
| WHE-1046: DEL dock 3 closed | T−144h to T−136h | Resolved before S2, S7 and S8 |
| WHE-1050: BOM labour shortage | T−96h to T−84h | Resolved before CHG-2311 |

## Documents

**Runbooks** (`docs/runbooks/*.pdf`): retrieve only register `status = current`.

| ID | Version | Status | Covers |
|---|---|---|---|
| RB-INV-001 | v2 | current | Inventory shortage (ALLOC-E101) |
| RB-ALLOC-002 | v3 | current | Allocation (ALLOC-E101, ALLOC-E107) |
| RB-ALLOC-002 | v2 | **superseded** | Old advice: the warehouse lead may release reservations over 24h old. v3 forbids that. |
| RB-CAR-003 | v4 | current | Carrier delay; codes WX-HOLD, HUB-CONG, ADDR-INC, NO-PICKUP, RTO-INIT |
| RB-PAY-004 | v2 | current | Payment hold; PAY-H201, PAY-H205, PAY-H210 |
| RB-WH-005 | v3 | current | Warehouse disruption; SYSTEM_DOWN, DOCK_CLOSED, POWER_OUTAGE, LABOUR_SHORTAGE |
| RB-CHG-006 | v1 | current | Change-related incident (before/after test) |

**Postmortems** (`docs/postmortems/*.pdf`): hints only, never proof of today's cause. PM-2025-052 is a scanned PDF (OCR).

| ID | Date | Scope | Role in the demo |
|---|---|---|---|
| PM-2026-009 | 2026-03-18 | WH-BLR-01, inventory sync | **Trap** for S11: similar, but current data rules it out |
| PM-2026-017 | 2026-05-22 | WH-BOM-01, allocation rule release | **Genuine hint** for S6: the current change log confirms it |
| PM-2025-041 | 2025-08-14 | Blue Dart Nagpur hub, weather | Consistent hint for S3 |
| PM-2026-004 | 2026-01-27 | WH-HYD-01, WMS outage | Consistent hint for S5 |
| PM-2025-052 | 2025-10-09 | National, credit-hold rule fault | Must **not** be applied to S4's single hold |
| PM-2026-021 | 2026-06-30 | WH-BLR-01, Delhivery feed delay | Explains why S9 must escalate |

No customer details appear in any document. Customer name, phone and address exist only in `orders`. The phone numbers are synthetic (`+91 98000` plus the order number).

## Golden questions

`golden_questions.jsonl` holds the 34 Gate 13 cases, one JSON object per line: 10 answerable, 5 insufficient evidence, 5 exact ID, 5 paraphrase, 3 delegation, 2 remote failure, 2 session isolation and 2 stale cache.

| Field | Meaning |
|---|---|
| `scenario` | The S-number above, or `healthy` |
| `setup` | What to do before asking (stop the specialist, change a row, open a second session). Empty means just ask. |
| `expected_outcome` | `cause_named`, `check_next`, `escalate`, `not_found`, `no_problem`, `partial`, `clarify`, `answer` or `retrieval_answer` |
| `fulfilable` | Answer to "can the assigned warehouse fulfil it": `yes`, `no`, `not_now`, `no_under_current_rule`, `unknown` or `not_applicable` |
| `must_mention` / `must_not_claim` | Facts the answer must contain, and claims that fail the case |
| `expected_docs` / `forbidden_docs` | Must appear in the top 5 retrieved / must never be cited. `@v2` means that version. |
| `expected_steps` / `forbidden_steps` | Trajectory check. The labels (`order_lookup`, `fulfilment_specialist`, `carrier_events`, `warehouse_events`, `change_log`, `knowledge_search`) are placeholders: map them to your tool names. |

Times such as "T-20h" in `must_mention` are relative to the run, like everything else in this file.
