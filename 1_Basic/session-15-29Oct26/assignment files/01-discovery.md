# 01 — Discovery

Questions to ask the customer before designing the orchestrator. Each one must change a design decision; "Why it matters" names that decision.

---

## Business

### 1. Peak load and what counts as resolved
- **Question:** Analysts start every investigation. How many run at the same time at peak (e.g. up to 1,000 analysts after a warehouse outage), and what must a finished investigation contain to count as resolved?
- **Why it matters:** Peak concurrency sets the rate limits, queueing and quotas on the shared warehouse, inventory, carrier and model APIs, so many analysts' investigations don't overload them. "Resolved" defines when the system may stop, what the output must contain, and the success metric (time to diagnose, analyst effort saved).

## Data

### 2. Source-of-truth systems
- **Question:** For each fact we need (order status, inventory, payment and credit hold, warehouse allocation, shipment status), which system is the authoritative source, and which systems only hold copies?
- **Why it matters:** Each tool must read from the system of record, and the conflict policy depends on it: when the ERP and the warehouse system disagree, the authoritative source wins over a lagging copy. Without it, conflicting evidence cannot be resolved by rules.

### 3. Data freshness and carrier latency
- **Question:** How quickly does each source reflect reality, how old can each kind of evidence be before it misleads, and how late do carrier events usually arrive?
- **Why it matters:** Sets the maximum age per evidence type in the freshness policy, so stale data (e.g. a four-hour-old inventory snapshot) is never treated as current, and a late carrier event is not mistaken for a carrier delay.

### 4. Inventory and payment semantics
- **Question:** What exactly do "available", "reserved" and "allocated" mean for inventory, and what do the payment states (approved, credit hold, risk review) mean and who can clear each one?
- **Why it matters:** The model reasons over these fields to find the cause. Without agreed definitions it misreads values such as "available: 1, required: 8" or treats a risk review as a credit hold, and the recommended action is wrong.

## Operations

### 5. Existing analyst workflow and explanation needs
- **Question:** How do analysts investigate an exception today (which systems first, how long it takes), and what must a recommendation show before they trust it and act on it?
- **Why it matters:** Gives the baseline for measuring time saved, shows good investigation paths for the golden test set, and defines the final output: evidence IDs, observed facts vs inferences, missing evidence.

### 6. Escalation rules and acceptable uncertainty
- **Question:** Which cases must always go to a person (high-value orders, VIP customers, credit or compliance holds, conflicting sources), and how uncertain may a recommendation be before it is escalated instead?
- **Why it matters:** Defines the human-review rules and the synthesis gate: when the system may conclude, when it must stop with insufficient evidence, and when it must escalate. "Cannot safely decide" becomes a valid outcome.

## Security and governance

### 7. Authorization scope
- **Question:** Who may investigate which orders (by customer, region, warehouse and role), and may every analyst see payment and credit evidence?
- **Why it matters:** Decides the trusted request context and the authorization check in the policy gate before each tool call. Identity and scope must come from the runtime, never from the model or the prompt.

### 8. Sensitive data
- **Question:** Which fields are sensitive (customer names, addresses, payment and pricing data, operational notes), which of them may be sent to Gemini, and what may be stored in traces and logs, and for how long?
- **Why it matters:** Decides which fields each tool passes to the model, what is masked or kept only as a reference in traces, and the retention rules. If payment data may not reach Gemini, only a summary such as "hold: yes, reason code" is passed.

## Reliability

### 9. API availability and retry expectations
- **Question:** What are the availability, latency and rate limits of each API (e.g. a warehouse API limited to 100 requests per minute), and is each call safe to retry after a timeout?
- **Why it matters:** Sets timeouts, retry rules with backoff, budgets and queueing; decides when to degrade or escalate instead of failing, and prevents retry storms when many analysts investigate at once.

## AI and orchestration

### 10. Model authority and investigation cost
- **Question:** What may the system decide on its own (read and recommend only, or ever take an action), and what is the maximum time and cost acceptable per investigation?
- **Why it matters:** Defines the allowed action space (read-only, no remediation), the runtime budgets (steps, model and tool calls, elapsed time) and the cost per investigation at the customer's daily volume.

---

## Path to autonomy (future, not in scope now)

Today an analyst starts every investigation and decides what to do with the recommendation. These steps would make the system autonomous, in this order. Each needs the customer's agreement, and each step's results must be measured before the next one.

1. **Start automatically on new exceptions.** An exception event (e.g. an order moving to `DELAYED` or `PAYMENT_HOLD`) starts the investigation, under a service identity instead of an analyst's. *Ask:* which exception types may be investigated without a request, and with what identity and data scope?
2. **Prioritize and queue.** Without an analyst choosing, the system decides what runs first: by order value, customer tier and SLA penalty, with rate limits and load shedding during bursts. *Ask:* how should business impact rank investigations?
3. **Group systemic incidents.** Many exceptions caused by one event (e.g. a warehouse-routing change) become one investigation with many linked orders, instead of hundreds of duplicates. *Ask:* who owns a systemic incident?
4. **Deliver results without being asked.** Findings are written to the order's case or ticket, and analysts are notified only when the result needs a person. *Ask:* where should results appear, and who gets notified?
5. **Run in shadow mode first.** The system investigates every exception in the background while analysts keep working as today; the two results are compared until accuracy is proven. *Ask:* what accuracy is needed before analysts rely on it?
6. **Propose actions with human approval.** The system proposes a remediation (e.g. request a credit review, request inventory reallocation, create a support case); a person approves; a separate service executes it with an idempotency key, an audit record and an undo path. *Ask:* which actions are allowed, and who approves each?
7. **Act automatically only on low-risk cases.** Policy may auto-approve narrow, reversible, clear-cut actions (e.g. opening a support case). High-impact actions (releasing a credit hold, reallocating inventory, cancelling, refunding) always need a person. *Ask:* which actions, if any, may run without approval?
