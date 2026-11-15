# Day 2 Reference Outcome
## Enterprise Semantic Order Exception & Fulfilment Orchestrator

This repository is a **participant reference implementation** for the Day-2
FDE Enterprise Semantic Orchestration Engineering Challenge.

Use it **after you have attempted your own architecture and implementation**.

It is not intended to be the only correct solution. The challenge deliberately
allows multiple valid orchestration trajectories.

---

## What this reference demonstrates

The central architecture is:

```text
Business objective
       ↓
Evidence register
       ↓
Gemini semantic orchestrator
       ↓
Structured NextAction
       ↓
Deterministic policy gate
       ↓
Execute ONE permitted action
       ↓
Normalize evidence
       ↓
Re-plan
       ↓
Grounded synthesis / safe termination
```

The key design rule is:

> **Gemini proposes. Software disposes. Evidence justifies.**

Gemini decides what evidence is useful next.

Python decides whether Gemini is allowed to execute that decision.

---

# 1. What you should compare with your own solution

Do not compare only the final answer.

Compare:

1. Where semantic reasoning lives.
2. Where deterministic policy lives.
3. Whether the model can invent actions.
4. Whether one decision executes one action.
5. How evidence provenance is retained.
6. How stale/conflicting evidence is represented.
7. How repeated actions are detected.
8. How premature synthesis is rejected.
9. How failures are normalized.
10. How the final conclusion references evidence IDs.
11. How the complete trajectory can be reconstructed.

---

# 2. Installation

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

source lab.env
```

Authenticate for Vertex AI if your environment requires it:

```bash
gcloud auth application-default login
gcloud config configurations activate "$TREDENCE_GCLOUD_CONFIG"
gcloud auth application-default set-quota-project "$GOOGLE_CLOUD_QUOTA_PROJECT"
```

---

# 3. Run deterministic tests first

These tests do not call Gemini.

```bash
pytest -q
```

They validate the engineering control plane:

```text
unknown action rejection
tool-call budget
same-action repetition
premature synthesis
forbidden write action
```

---

# 4. Inspect the scenarios

```bash
python -m app.cli --list
```

The reference includes cases representing:

```text
ORD-1001  payment / credit exception
ORD-1002  inventory / warehouse exception
ORD-1003  recent operational-change hypothesis
ORD-1004  conflicting evidence
ORD-1005  stale inventory evidence
```

---

# 5. Run a live semantic investigation

```bash
python -m app.cli ORD-1001
```

Then:

```bash
python -m app.cli ORD-1002
python -m app.cli ORD-1003
```

Do not expect the exact same trajectory every time.

What should remain stable is:

```text
allowed action vocabulary
schema validation
policy enforcement
budgets
evidence provenance
termination requirements
```

The semantic trajectory may vary because Gemini is interpreting the evidence.

---

# 6. What a trace looks like

A run prints events similar to:

```text
STEP 1
PROPOSED : GET_ORDER
POLICY   : ALLOW
EXECUTED : GET_ORDER
EVIDENCE : EV-001

STEP 2
PROPOSED : CHECK_PAYMENT_HOLD
POLICY   : ALLOW
EXECUTED : CHECK_PAYMENT_HOLD
EVIDENCE : EV-002

STEP 3
PROPOSED : SYNTHESIZE
POLICY   : ALLOW
```

Another order may produce:

```text
GET_ORDER
→ CHECK_WAREHOUSE
→ CHECK_INVENTORY
→ SYNTHESIZE
```

That difference is the point.

---

# 7. Important: this is not a hard-coded router

Open:

```text
app/orchestrator.py
```

The runtime does **not** contain business routing such as:

```python
if payment_hold:
    call_payment()
elif inventory_problem:
    call_inventory()
```

Instead, Gemini receives:

```text
objective
available action contracts
current evidence
previous trajectory
```

and returns a structured `NextAction`.

The deterministic policy then validates that proposal.

---

# 8. Evidence register

Open:

```text
app/evidence.py
```

Every tool result becomes evidence containing:

```text
evidence_id
source_action
source_system
observed_at
source_timestamp
status
freshness_seconds
payload
```

The final answer should therefore be able to distinguish:

```text
observed fact
inference
missing evidence
recommendation
```

---

# 9. Failure handling

The reference normalizes tool failures rather than exposing arbitrary Python
exceptions as the orchestration contract.

A tool result can become:

```text
SUCCESS
NOT_FOUND
TIMEOUT
DEPENDENCY_UNAVAILABLE
STALE_EVIDENCE
```

A production implementation would normally add retries, backoff, distributed
tracing, persistent execution state and service-level authorization.

Those are intentionally identified as production extensions rather than hidden
inside this reference.

---

# 10. Try changing the evidence

This is the most important experiment.

Open:

```text
data/orders.json
data/payments.json
data/inventory.json
data/warehouses.json
data/changes.json
```

Change one meaningful fact.

For example, change a payment hold from:

```json
"credit_hold": true
```

to:

```json
"credit_hold": false
```

Run the same order again.

Ask:

```text
Did the trajectory change?
Why?
Did the deterministic policy change?
```

The policy should not change merely because the evidence changed.

---

# 11. Files to study

Recommended sequence:

```text
app/contracts.py
        ↓
app/evidence.py
        ↓
app/policy.py
        ↓
app/tools.py
        ↓
app/semantic.py
        ↓
app/orchestrator.py
        ↓
app/synthesis.py
```

---

# 12. What is deliberately not implemented

This participant reference does not pretend to be a complete enterprise
platform.

It intentionally does not include:

```text
autonomous write/remediation actions
IAM/authentication
distributed durable workflow recovery
message queues
centralized observability backend
production secrets
distributed rate limiting
human approval UI
```

A strong FDE should be able to explain where those capabilities would fit.

---

# 13. Production extension

A production deployment could evolve toward:

```text
API / Cloud Run
      ↓
Orchestration Service
      ↓
Vertex AI Gemini
      ↓
Enterprise APIs

plus:

Secret Manager
Cloud Logging / Monitoring / Trace
queue/backpressure layer
persistent evidence + execution store
service identity / IAM
human approval workflow
```

Do not add services merely because they are available. Every component should
exist for an engineering reason.

---

# 14. The expected learning outcome

After studying this reference you should be able to explain:

> Why is this not a fixed workflow?

> Why is this not an unrestricted autonomous agent?

> Why is semantic reasoning separated from deterministic execution control?

> Why does evidence provenance matter?

> Why can Gemini propose STOP while software still rejects STOP?

> How would you make this architecture production-ready?

If you can defend those decisions, you have understood the purpose of Day 2.
