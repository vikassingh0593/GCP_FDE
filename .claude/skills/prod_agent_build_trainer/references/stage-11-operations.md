# Stage 11: Operations and delivery

**Goal:** someone else can run, debug, change and roll back this system after you leave.
**Never skip this stage.**
**Go deeper:** concepts.md §25–§27; arch.md flows 3 and 7.

## What to log per request

`correlation_id` · `invocation_id` · target ID · `decision_id` · step number · proposed action · policy decision · executed action · tool latency and status · retry count · evidence ID · model latency · token usage · estimated cost · elapsed time · termination reason · `model_id` · `prompt_version` · `policy_version` · `tool_contract_version`

A support engineer must be able to rebuild: request → decision → policy → tool → evidence → next decision → ending → recommendation.

## The runbook covers

Gemini unavailable · a key API unavailable · high policy rejection rate · repeated-action spike · latency spike · token or cost spike · wrong orchestration behavior · bad prompt release · bad policy release · rollback.

## Checks

### OP-01 · High · One structured log row per request
- **Look for:** the fields above, as structured data, with the correlation ID.
- **Why:** print statements can't be queried at 3 a.m. during an incident.
- **Fix:** log to Cloud Logging, and route to BigQuery.

### OP-02 · High · Versions are recorded with every run
- **Look for:** model, prompt, decision schema, policy and tool contract versions.
- **Why:** without them you can't explain a past answer, or roll back to what worked.
- **Fix:** log them, and treat them as a release set.

### OP-03 · High · Metrics and alerts mean something
- **Look for:** alerts on latency, block rate, escalation rate, 429s, cost per task and freshness.
- **Why:** alerting on every recoverable event trains people to ignore alerts. Govern on more than accuracy.
- **Fix:** pick a few top alerts, each with a runbook entry.

### OP-04 · High · Failures are never silent (scan)
- **Look for:** `except Exception: pass`, or a tool failure with nothing logged.
- **Why:** in one real build, a first search failed and nothing appeared in the log, so the problem was invisible until a person noticed.
- **Fix:** log an error row with the traceback for every tool failure.

### OP-05 · High · Model and parser lifecycles are tracked
- **Look for:** a list of retirement dates, and a scheduled check.
- **Why:** a retired model stops the system on a known date, and a parser update can change every chunk.
- **Fix:** watch the lifecycle pages, and migrate early, with a full evaluation.

### OP-06 · High · The degraded mode is decided before the outage
- **Look for:** what happens when Gemini or a dependency fails: bounded retry, fallback model, deterministic degradation, queueing or escalation.
- **Why:** decided during an outage, it will be wrong. A fallback model is a different model, so evaluate it first.
- **Fix:** write the plan, and test it.

### OP-07 · Medium · Recovery after a crash is explained
- **Look for:** what happens if the process dies at step 4: execution ID, saved evidence and decisions, resume or restart, duplicate calls, checkpoint boundary.
- **Why:** long investigations will be interrupted, and in-memory state vanishes.
- **Fix:** design it, and separate what is built from what is planned.

### OP-08 · Medium · Cost and latency are estimated
- **Look for:** model calls, tool calls, tokens and cost per task, plus a p95 latency budget split across steps.
- **Why:** cost per successful task decides whether the system is worth running.
- **Fix:** multiply by daily volume. Ways to reduce it: less context, reused evidence, deterministic short-circuits, cheaper models where measured good enough.

### OP-09 · High · Cache keys include version and access
- **Look for:** keys with corpus version, access rights and freshness.
- **Why:** a fast stale answer is still wrong, and a shared cache can leak one user's answer to another.
- **Fix:** add them to every key. Cache per-user data only per user.

### OP-10 · High · A runbook exists
- **Look for:** the scenarios above, each with symptoms, first steps and rollback.
- **Why:** the person on call may not be you.
- **Fix:** write it, and practice one scenario.

### OP-11 · High · A change is a release, and rollback restores everything
- **Look for:** separate environments, CI from Git, one artifact promoted, and rollback of code, prompt and index together.
- **Why:** a prompt or policy change can alter behavior as much as code, and restoring code alone leaves a mismatched system.
- **Fix:** version all of them together. Use canary rollout and feature flags.

### OP-12 · Medium · Dependencies are pinned (scan)
- **Look for:** exact versions or a lock file, and vulnerability scanning.
- **Why:** a range such as `>=2.0,<3.0` means two builds can differ, and an ADK update can change behavior.
- **Fix:** pin versions or use a lock file, and update on purpose.

### OP-13 · Medium · SLOs and an owner exist
- **Look for:** targets for availability, latency, unsupported-claim rate and task success, plus a named owner.
- **Why:** "who owns this after the FDE leaves?" has to have a real answer.
- **Fix:** agree SLOs and an error budget, and hand over.

### OP-14 · Medium · Future writes are designed to be idempotent
- **Look for:** an idempotency key, operation ID, deduplication and a status lookup.
- **Why:** a lost response after a successful write must not create a duplicate enterprise action.
- **Fix:** design this before adding any write, even a simple one. See arch.md flow 4.

### OP-15 · Note · Recovery is tested
- **Look for:** restored backups, tested failover, and versioned indexes (beyond the course).
- **Why:** a backup you have never restored isn't a backup.
- **Fix:** run a restore drill.

### OP-16 · High · Cache lifetimes follow each source's change rate
- **Look for:** one TTL for everything; live state (inventory, balances) or a final answer built on live data served from a cache.
- **Why:** a cache can never be fresher than its source. A cached "in stock" answer stays wrong for the whole TTL after the stock is gone.
- **Fix:** set the lifetime per data type: query embeddings until the model changes, retrieval results about a day and cleared with the index version, live state not cached (or under the source's refresh cycle), final answers on live data not cached. Write the table in the decision matrix.
- **Go deeper:** concepts.md §25 (lifetime by data type).

## Local → production

| Lab | Production |
|---|---|
| Health report from log tables | Dashboards and alerts in Cloud Monitoring and Looker Studio |
| Deploy from a laptop | Separate projects, CI/CD, signed artifacts, gated promotion |
| One project and region | Agreed SLOs, tested failover and restores |

## Defend it

- How would you debug a bad recommendation from last Tuesday?
- How do you roll back a bad prompt?
- How do you detect rising cost?
- How do you prove analyst time was saved?
- Who owns this after you leave?
