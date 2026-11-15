# Stage 1: Discovery and scope

**Goal:** understand the enterprise problem before choosing any model or service.
**Never skip this stage.** The answers change the architecture, and rework later costs far more.
**Go deeper:** concepts.md §28 (FDE practice).

## Build steps

1. Write the business objective: who uses it, what they do today, and what a finished result must contain.
2. Ask at least 10 questions across business, data, operations, security and governance, reliability, and AI. Each must change a design decision. Write the question and why it matters.
3. Mark the **blockers**: answers you must have before finalizing the design.
4. Write the production boundary: what the first version may do, and what it must not do.
5. Write requirements in separate groups: functional, non-functional, security, reliability, observability, AI quality, operational, and explicit non-goals.
6. Fill the decision table and the decision matrix below.
7. Keep a decision log: "I selected ___ because the workflow requires ___. The constraints are ___. We will evaluate it with ___. I would change it if ___."

### Discovery areas

| Area | Ask about |
|---|---|
| Business | Objective, peak load, what "resolved" means, success metric and baseline |
| Data | Source of truth per fact, what each field really means, freshness, versions, jurisdiction, tables, scans |
| Operations | Current workflow, what users need to see before they trust a result, escalation rules |
| Security and governance | Who may see what, sensitive fields, what may reach the model, audit, retention |
| Reliability | API limits, availability, latency, which calls are safe to retry, what happens when a source is down |
| AI and orchestration | What the model may decide, acceptable uncertainty, cost and time per task |

### Decision table: decide and justify before coding

Session storage · where authorization comes from · cross-unit access · what is logged · how repeated calls are handled · the failure taxonomy · where telemetry lives · who enforces policy · how much autonomy the agent gets.

### Decision matrix: who decides what

| Decision | Model | Code | Person |
|---|---|---|---|
| Interpret ambiguous evidence | ✓ | | |
| Propose the next step | ✓ | | |
| Suggest a likely cause | ✓ | | |
| Validate the action vocabulary | | ✓ | |
| Enforce authorization and budgets | | ✓ | |
| Decide retries and freshness | | ✓ | |
| Approve high-impact actions | | | ✓ |
| Override a compliance hold | | | ✓ |

## Checks

### DS-01 · High · Starts from the problem, not the model
- **Look for:** users, data, authority boundaries, failure modes and operating needs written down before any technology choice.
- **Why:** a design built around a model answers the wrong question well.
- **Fix:** write the objective and failure modes first, then decide where AI belongs. Facts that must be exact or carry legal weight belong in databases, rules and APIs, not in a model.

### DS-02 · High · A source of truth is named for every fact
- **Look for:** for each fact, which system is authoritative and which only hold copies.
- **Why:** without this, conflicts can't be settled by rules, and metadata ends up guessed from text.
- **Fix:** list each fact with its owning system. The conflict policy in Stage 5 depends on this.

### DS-03 · High · The action boundary is explicit
- **Look for:** a written list of what the system may do and what it must not do, for example read and recommend only.
- **Why:** an agent with write access and no boundary can change real systems on a wrong guess.
- **Fix:** start read-only. List forbidden actions by name. Writes need authorization, approval, idempotency and audit, added deliberately.

### DS-04 · High · Success is measurable, with a baseline
- **Look for:** a metric such as time to diagnose or analyst effort saved, plus today's number.
- **Why:** without a baseline you can't prove value, and "it works" is only an opinion.
- **Fix:** measure the current process during discovery.

### DS-05 · High · Freshness needs are known per data type
- **Look for:** how old each kind of data may be before it misleads, and how late sources usually arrive.
- **Why:** a healthy nightly pipeline still misses a same-day need. A four-hour-old stock figure can look like the truth.
- **Fix:** write the maximum age per evidence type. It becomes the freshness policy in Stage 5.

### DS-06 · High · Access and sensitive data are understood
- **Look for:** who may see what, which fields are sensitive, what may reach the model, and what may be logged and for how long.
- **Why:** these rules are hard to add later, and they change what tools return.
- **Fix:** answer them now. If payment data may not reach the model, a tool passes only a summary such as "hold: yes, reason code".

### DS-07 · Medium · Peak load and dependency limits are known
- **Look for:** peak concurrent users, and each API's rate limit and availability.
- **Why:** a model can't reason its way past a warehouse API limited to 100 requests per minute.
- **Fix:** collect the numbers. They set queues, quotas and retries in Stages 6 and 8.

### DS-08 · Medium · Escalation and uncertainty are defined
- **Look for:** which cases always go to a person, and how uncertain a result may be.
- **Why:** "I can't safely decide" is a valid production result only if someone has defined it.
- **Fix:** write the escalation rules, for example high-value orders, compliance holds, conflicting sources.

### DS-09 · Medium · Cost and time per task are agreed
- **Look for:** a maximum cost and time per task.
- **Why:** moving from three model calls to seven is a large bill at 20,000 tasks a day.
- **Fix:** agree limits. They become runtime budgets in Stage 6.

### DS-10 · Medium · Every question changes a decision
- **Look for:** each question linked to the decision it affects.
- **Why:** questions that change nothing waste the customer's time.
- **Fix:** drop or rewrite any question whose answer wouldn't change the design. For example, the business cost of an exception doesn't matter if an analyst always picks what to investigate, but it does if the system must prioritize on its own.

### DS-11 · Medium · Assumptions and blockers are recorded
- **Look for:** an assumptions list, with what would change if each were wrong.
- **Why:** unspoken assumptions become production incidents.
- **Fix:** keep them in the design document, and review them with the customer.

### DS-12 · Note · Autonomy grows in measured steps
- **Look for:** a path such as: analyst-started → automatic start → shadow mode → proposals with approval → automatic only for narrow, reversible cases.
- **Why:** trust is earned with measurement, and high-impact actions always keep a person in the loop.
- **Fix:** write the path as future work, and measure each step before the next.

## Defend it

- Why not begin with the model?
- Which of your questions changed the design, and how?
- Which decisions belong to the model, to code, and to a person?
- Who owns this system after you leave?
