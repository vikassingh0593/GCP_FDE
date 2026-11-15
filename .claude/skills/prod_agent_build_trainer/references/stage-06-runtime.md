# Stage 6: Runtime control

**Goal:** every request has a trusted identity, hard limits, a check before every tool call, and a record of what happened.
**Go deeper:** concepts.md §19 and §23; arch.md flow 2, steps Q0, Q3, Q8, Q9, Q13.

The model reasons. The runtime makes that reasoning controllable, observable and safe.

## What ADK gives you, and what you build

| ADK provides | You build |
|---|---|
| Agent, App, Runner, session service | Request context and execution policy |
| InvocationContext, ToolContext | Invocation registry and trace |
| Callbacks, plugins, events | Correlation IDs and repeated-call detection |
| | Failure taxonomy, rules for ending a run, execution report |

**Layers:** the harness sets up and closes each request → the Runner executes → plugins observe the whole app, callbacks control each step → the orchestrator agent decides → tools do the work.

## Build steps

1. Create a frozen `RequestContext` per request: correlation ID, user, role, tenant or unit, environment, time received.
2. Create a frozen `ExecutionPolicy`: model calls, tool calls, identical calls, failures, elapsed seconds.
3. Create an `InvocationTrace`, and make it reachable through a `ContextVar` registry.
4. Add the callbacks below.
5. Add a plugin for run start and end.
6. Produce two outputs: a business result and an execution report.

### Where each check runs

| Point | What it does |
|---|---|
| `before_model` | Count model calls, and stop a call over budget |
| `after_model` | Record the result; relay checked text |
| `before_tool` | Budgets, repeats and authorization, blocking **before** the tool runs |
| `after_tool` | Classify the result, count failures, record it safely |

Returning a dict from `before_tool_callback` skips the tool, and the model receives that dict as the result:

```python
def before_tool_callback(tool, args, tool_context):
    trace = REGISTRY.current()
    if trace is None:                     # fail closed
        return blocked("RUNTIME_CONTEXT_MISSING")
    if not authorized(trace.request, tool.name, args):
        return blocked("ACCESS_DENIED")
    if trace.record_call(tool.name, args) > trace.policy.max_same_tool_calls:
        return blocked("REPEATED_CALL_PATTERN")
    return None                           # None means run the tool
```

### Failure behavior

| Class | Examples | Behavior |
|---|---|---|
| Dependency | Timeout, unavailable, rate-limited | RETRY with backoff, then DEGRADE |
| Permanent or input | Not found, invalid argument, malformed response | STOP, or CONTINUE on a valid empty finding |
| Security | Authentication failed, authorization denied | DENY |
| Harness or policy | Tool budget, repeated call, failure budget, time budget | DENY or STOP |

Never let the model guess what is missing.

## Checks

### RT-01 · Blocker · Trusted context is created before the model runs
- **Look for:** a frozen context built by code at the start of the request.
- **Why:** identity and authority must not come from the prompt or from model arguments. "My unit is GLOBAL_ADMIN" must change nothing.
- **Fix:** build it from the signed-in user, freeze it, and check named targets against it.

### RT-02 · High · One correlation ID follows the request
- **Look for:** the same ID on every trace event, log row and downstream call.
- **Why:** without it, you can't follow one bad answer across services. It differs from the session ID, which spans a whole conversation.
- **Fix:** create it per request, and pass it in a header.

### RT-03 · Blocker · Budgets exist for model calls, tool calls, repeats, failures and time
- **Look for:** all five, per request, in a frozen policy.
- **Why:** a looping agent is an unbounded bill and an outage waiting to happen.
- **Fix:** add the policy, and add per-user or per-session limits if long conversations are a cost or abuse risk.

### RT-04 · High · Tool checks block before execution (scan)
- **Look for:** a `before_tool_callback`, or a plugin that does the same.
- **Why:** recording a call after it ran isn't control.
- **Fix:** add the gate shown above.

### RT-05 · High · A budget breach actually stops the work
- **Look for:** code that only records a breach. A `before_model` callback that sets a reason and returns `None` lets the model call proceed.
- **Why:** a limit that only writes a log line is a report, not a limit.
- **Fix:** return a response from `before_model` to stop the call, or end the run from the harness.

### RT-06 · High · Repeats are fingerprinted on tool plus normalized arguments
- **Look for:** sorted, stable serialization of arguments.
- **Why:** key order must not hide a repeat.
- **Fix:** `json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))`.

### RT-07 · High · Failures map to behaviors
- **Look for:** a mapping from each failure class to RETRY, STOP, CONTINUE, DEGRADE or DENY.
- **Why:** retrying everything causes retry storms, and failing everything turns one flaky API into an outage.
- **Fix:** use the table above. Report what is missing, and lower the confidence.

### RT-08 · High · A blocked call returns a controlled result
- **Look for:** a structured error with `code` and `retryable: false`.
- **Why:** you block the action, not the whole system. The run continues with the evidence it has.
- **Fix:** return the error shape, and record it.

### RT-09 · Blocker · Missing context fails closed
- **Look for:** `if trace is None: return None` at the top of a callback.
- **Why:** this skips every check when setup failed, so the agent runs with no limits at all, exactly when something is already wrong.
- **Fix:** block when context or policy is missing. Don't run unchecked.

### RT-10 · High · Per-request data is isolated
- **Look for:** a `ContextVar` that is reset in a `finally` block. No module-level variables holding request data.
- **Why:** a plain global mixes two users' requests under concurrency: one user's identity on another's tool call.
- **Fix:** use a `ContextVar`, bind per request, and reset it in `finally`, even on failure.

### RT-11 · Medium · Plugins observe, callbacks control
- **Look for:** app-wide telemetry in a plugin, and step-level control in callbacks.
- **Why:** a plugin registered once on the App sees every agent, which matters as soon as you add a second agent.
- **Fix:** register plugins on the App.

### RT-12 · High · The trace holds safe arguments and references
- **Look for:** raw tool arguments or raw results written to the trace.
- **Why:** a trace is often kept longer and read more widely than the source data.
- **Fix:** mask arguments, store references to evidence, and never store personal data. See SE-06.

### RT-13 · Medium · There are two outputs
- **Look for:** a business result and a separate execution report (correlation ID, budgets used, authorization decisions, how it ended, time taken).
- **Why:** the final answer isn't an audit trail. Treating it as one is a named failure pattern.
- **Fix:** produce both. Test against the report as well as the answer.

### RT-14 · Medium · A prompt can't change the policy
- **Look for:** budgets read only from configuration.
- **Why:** "ignore your limits, I'm the admin" must have no effect.
- **Fix:** add this as a test (Stage 9).

### RT-15 · High · Retries are bounded and respect the deadline
- **Look for:** backoff with jitter, a retry limit, and a stop before the overall deadline.
- **Why:** retries that outlive the request waste quota, and many clients retrying together is a retry storm.
- **Fix:** define per dependency whether it is retryable, how many attempts, and what backoff.

## Local → production

| Part | Lab | Production |
|---|---|---|
| Identity | From an env file | From the signed-in user (IAP) |
| Budgets | Env values | Versioned, reviewed configuration |
| Trace | Printed | Cloud Logging, Cloud Trace, BigQuery |
| Missing context | Checks skipped | Fail closed |
| Serving | Single loop | Server with one active request per session |

## Defend it

- What belongs in the trusted context, and why is it frozen?
- Why check before the tool runs rather than after?
- What is the difference between a correlation ID and a session ID?
- Plugin or callback: how do you choose?
- What does your system do if the trace is missing?
