---
source_id: INV-POLICY-2026-V3
status: APPROVED
version: "3.0"
title: Inventory Freshness Standard
effective_date: 2026-08-01
---

# Inventory Freshness Standard

## 4.2 Inventory Evidence Freshness
For the Stockout Decision Agent, inventory evidence used for an operational recommendation must not be older than **15 minutes** at decision time.

## 4.3 Available Inventory
Available inventory is defined as on-hand inventory minus reserved inventory minus damaged inventory.

## 7.4.2 Offline Store Exception
When a store is confirmed offline and a fresh synchronization cannot be obtained, the agent may use an inventory snapshot up to **45 minutes** old. The answer must explicitly identify the store as offline and qualify the evidence as stale-but-permitted under this exception.

## 8.1 Authority
This version supersedes Inventory Freshness Standard V2. Approved V3 rules are authoritative for the Stockout Decision Agent.
