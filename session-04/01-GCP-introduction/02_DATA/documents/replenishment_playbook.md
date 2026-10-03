---
source_id: REPL-PLAYBOOK-2026
status: APPROVED
version: "1.4"
title: Replenishment Response Playbook
effective_date: 2026-08-15
---

# Replenishment Response Playbook

## 3.1 Immediate Replenishment Review
If projected inventory becomes negative within the next six hours after considering eligible inbound supply, initiate an **Immediate Replenishment Review**.

## 3.2 Inbound Eligibility
Only shipments with status `IN_TRANSIT` and an ETA inside the decision horizon are eligible by default. Delayed, cancelled or out-of-horizon shipments require an explicit approved override.

## 5.3 Inter-store Transfer
An inter-store inventory transfer requires human approval. The agent may recommend the transfer but must not represent it as already approved.
