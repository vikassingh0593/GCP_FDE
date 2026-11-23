# Enterprise ADK Runtime --- Participant Concept Guide

## 1. What Are We Building?

Consider a production incident:

> **INC-5037:** Checkout failures and payment latency are increasing.

An AI incident investigator may need to:

1.  retrieve the incident record;
2.  inspect service telemetry;
3.  inspect recent deployments;
4.  search similar historical incidents;
5.  reason over the evidence;
6.  produce a grounded conclusion.

The agent has capabilities such as:

``` text
get_incident()
get_service_metrics()
get_recent_deployments()
search_historical_incidents()
```

But an enterprise system must also answer:

-   Who is executing the request?
-   Which conversation does it belong to?
-   How many model and tool calls are allowed?
-   What happens when a tool fails?
-   What if the agent repeatedly calls the same tool?
-   How do we observe and explain the execution?
-   How do we stop pathological execution?

> **The model reasons. The runtime harness makes that reasoning
> operational, observable, and controllable.**

------------------------------------------------------------------------

## 2. High-Level Architecture

``` mermaid
flowchart TB
    U[User Request] --> RC[Trusted Request Context] --> R[Runner]
    R <--> SS[Session Service]
    R --> A[Agent]
    A <--> M[Gemini]
    M -->|proposes tool| BC[Before Tool Callback]
    BC --> P[Execution Policy]
    P -->|allow| T[Enterprise Tool]
    P -->|block| X[Controlled Policy Result]
    T --> AC[After Tool Callback] --> M
    PL[Plugin] -. observes runtime .-> R
    PL -. observes .-> M
    PL -. observes .-> T
    BC --> TR[Invocation Trace]
    AC --> TR
    PL --> TR
    TR --> REP[Execution Report]
```

The **Agent is only one component** of the complete runtime.

------------------------------------------------------------------------

## 3. Agent

The **Agent** defines AI behavior:

``` text
Which model should reason?
What instructions should it follow?
Which tools can it use?
Which callbacks participate in its lifecycle?
```

Think of it as:

> **The definition of an AI worker and the capabilities available to
> it.**

------------------------------------------------------------------------

## 4. App

The **App** is the application-level container around the agent runtime.

``` text
APP
├── Root Agent
└── Application-level runtime capabilities
    └── Plugins
```

The Agent describes AI behavior. The App represents the larger ADK
application in which that behavior operates.

------------------------------------------------------------------------

## 5. Runner

The **Runner** is the runtime engine that executes the agent.

``` text
Agent  = What should behave?
Runner = Execute that behavior.
```

Conceptually:

``` text
User Message
     ↓
   Runner
     ↓
   Agent
     ↓
   Model
     ↓
 Tool Calls
     ↓
   Events
     ↓
 Final Response
```

A useful description is:

> **Runner = ADK runtime execution engine / coordinator.**

Do not confuse the Runner with higher-level workflow orchestration such
as sequential execution, parallel execution, routing, loops, or graph
workflows.

------------------------------------------------------------------------

## 6. Session Service and InMemorySessionService

A conversation can contain multiple turns. Something must manage the
session containing those turns.

``` text
Runner
   │
   ├── "Give me session ABC123"
   ▼
Session Service
   ▼
Session ABC123
```

For this lab:

``` python
session_service = InMemorySessionService()
```

The session is held in the running Python process:

``` text
Python starts
    ↓
Session exists in memory
    ↓
Conversation executes
    ↓
Python stops
    ↓
In-memory session disappears
```

------------------------------------------------------------------------

## 7. Session vs Invocation

This distinction is fundamental.

``` text
ONE SESSION
│
├── INVOCATION 1
│   "Investigate INC-5037"
│
├── INVOCATION 2
│   "Now check the deployment"
│
└── INVOCATION 3
    "Compare historical incidents"
```

> **Session = conversation scope across turns.**

> **Invocation = one execution triggered by one user request.**

A session can contain many invocations.

------------------------------------------------------------------------

## 8. InvocationContext

During one invocation, ADK maintains runtime information associated with
that execution.

``` text
INVOCATION
├── current agent
├── session
├── invocation identity
├── runtime information
└── execution-scoped context
```

> **InvocationContext = ADK runtime context surrounding the current
> invocation.**

Mental model:

``` text
SESSION
├── Invocation
│   └── InvocationContext
├── Invocation
│   └── InvocationContext
└── Invocation
    └── InvocationContext
```

------------------------------------------------------------------------

## 9. RequestContext in This Lab

Enterprise applications often have trusted information that should
originate from the application rather than from the model.

``` text
RequestContext
├── correlation_id
├── tenant_id
├── user_id
├── environment
└── received_at
```

This is **our application architecture**, not a replacement for ADK's
InvocationContext.

> **Trusted identity, tenant, and runtime policy should come from
> trusted application context---not from arguments invented by the
> model.**

------------------------------------------------------------------------

## 10. Model Calls

One invocation may contain multiple model calls.

``` text
Invocation
├── Model Call 1
├── Tool Call
├── Model Call 2
├── Tool Call
└── Model Call 3
```

This matters because model calls and tool calls can have independent
execution budgets.

------------------------------------------------------------------------

## 11. Tool Call and ToolContext

The model can propose a tool call:

``` text
get_service_metrics(
    service_name="payments-api"
)
```

The runtime processes that proposed action:

``` text
Gemini
   │ proposes
   ▼
Tool Call
   ↓
Runtime
   ↓
Python Tool
   ↓
Enterprise System
```

When a particular tool is executing, ADK provides **ToolContext** around
that execution.

``` text
SESSION
└── INVOCATION
    └── InvocationContext
        ├── Model Call
        └── Tool Call
            └── ToolContext
```

Model-generated tool arguments and runtime ToolContext are different
concepts.

------------------------------------------------------------------------

## 12. Callbacks

Callbacks are interception points in the execution lifecycle.

Instead of:

``` text
Model → Tool → Model
```

we can have:

``` text
Model
  ↓
Before Tool Callback
  ↓
Tool
  ↓
After Tool Callback
  ↓
Model
```

Callbacks can help:

-   observe execution;
-   validate actions;
-   enforce policy;
-   collect metrics;
-   inspect failures;
-   block actions when required.

### Model callbacks

``` text
before_model
     ↓
   MODEL
     ↓
after_model
```

These let the runtime observe model boundaries and count model
interactions.

### Before-tool callback

``` text
Gemini proposes tool
        ↓
BEFORE TOOL CALLBACK
        ↓
Execution Policy
        ↓
   ┌────┴────┐
 ALLOW     BLOCK
   ↓          ↓
 Tool     Policy Result
```

### After-tool callback

``` text
Tool
 ↓
Result
 ↓
AFTER TOOL CALLBACK
 ↓
Inspect status / failure / metrics
 ↓
Model
```

------------------------------------------------------------------------

## 13. Plugin

Some concerns apply across the application runtime.

Examples:

``` text
telemetry
correlation
metrics
invocation lifecycle
cross-cutting observability
```

Conceptually:

``` text
                    APP
                     │
          ┌──────────┴──────────┐
          │                     │
       PLUGIN                 AGENT
          │                     │
 cross-cutting              callbacks
 runtime concerns              │
          │               agent-specific
 telemetry                   controls
 tracing
 metrics
```

A useful distinction:

> **Plugin = application-wide cross-cutting runtime concern.**

> **Callback = interception/control at a specific agent lifecycle
> boundary.**

------------------------------------------------------------------------

## 14. Execution Policy

Prompts influence probabilistic behavior. Enterprise limits should be
deterministic.

``` text
ExecutionPolicy
├── max model calls
├── max tool calls
├── max repeated identical calls
├── max failures
└── max elapsed time
```

Example:

``` text
Model calls       3 / 6
Tool calls        5 / 8
Failures          1 / 2
Elapsed           12.4 / 45 seconds
```

> **Prompts influence behavior. Runtime policy constrains behavior.**

------------------------------------------------------------------------

## 15. Repeated-Call Detection

A system may still be below its total tool budget while behaving
pathologically:

``` text
get_service_metrics(payments-api)
get_service_metrics(payments-api)
get_service_metrics(payments-api)
get_service_metrics(payments-api)
```

The harness fingerprints:

``` text
tool name + normalized arguments
```

and counts repeated proposals.

If the configured threshold is exceeded:

``` text
REPEATED_CALL_PATTERN
```

can be generated.

> **An enterprise runtime should be able to protect the system from
> pathological agent behavior.**

------------------------------------------------------------------------

## 16. Failure Taxonomy

Not every failure means the same thing.

``` text
DEPENDENCY_TIMEOUT
DEPENDENCY_UNAVAILABLE
RATE_LIMITED

NOT_FOUND
INVALID_ARGUMENT
MALFORMED_RESPONSE

AUTHENTICATION_FAILED
AUTHORIZATION_DENIED

TOOL_BUDGET_EXCEEDED
REPEATED_CALL_PATTERN
FAILURE_BUDGET_EXCEEDED
INVOCATION_TIME_BUDGET_EXCEEDED
```

A useful classification:

``` text
Failure
├── Dependency failure
├── Permanent/input failure
├── Security failure
└── Harness/policy failure
```

Structured failures make runtime behavior easier to control and explain.

------------------------------------------------------------------------

## 17. Events

An execution is not only:

``` text
Input → Final Answer
```

The Runner exposes an event stream representing activity during
execution.

``` text
User Request
     ↓
Model activity
     ↓
Function call
     ↓
Function response
     ↓
More model activity
     ↓
Final response
```

Events allow us to inspect the execution trajectory rather than only the
final answer.

------------------------------------------------------------------------

## 18. Invocation Trace

The lab converts runtime activity into a normalized trace.

``` text
01. REQUEST_ACCEPTED
02. PLUGIN_BEFORE_RUN
03. BEFORE_MODEL
04. AFTER_MODEL
05. TOOL_PROPOSED
06. TOOL_ALLOWED
07. TOOL_COMPLETED
08. BEFORE_MODEL
09. AFTER_MODEL
10. PLUGIN_AFTER_RUN
11. INVOCATION_END
```

The trace helps answer:

``` text
What did the model do?
Which tools did it request?
Which actions were allowed?
Which failed?
How many model calls occurred?
How many tool calls occurred?
Why did execution terminate?
```

------------------------------------------------------------------------

## 19. Correlation ID

Each request receives a correlation ID:

``` text
corr-71a93c...
```

Conceptually it can connect:

``` text
Incoming request
├── Agent execution
├── Tool calls
├── Enterprise API logs
├── Errors
└── Execution report
```

This becomes important when many invocations execute concurrently.

------------------------------------------------------------------------

## 20. Execution Report

The final answer explains what the agent concluded.

The execution report explains **how the runtime behaved**.

``` text
ENTERPRISE ADK INVOCATION REPORT

Correlation ID : corr-81a3...
Tenant         : tenant-retail-a
Termination    : NORMAL

Model calls    : 3 / 6
Tool calls     : 3 / 8
Failures       : 0 / 2
```

Two views matter:

``` text
BUSINESS VIEW
"What did the agent conclude?"

ENGINEERING VIEW
"How did the agent execute?"
```

------------------------------------------------------------------------

## 21. Complete Mental Model

``` mermaid
flowchart TB
    U[USER] --> RC[Trusted Request Context] --> R[RUNNER]
    R <--> SS[SESSION SERVICE]
    SS --> S[SESSION]
    R --> I[INVOCATION]
    I --> IC[InvocationContext]
    IC --> A[AGENT]
    A --> M[GEMINI]
    M -->|tool proposal| BT[Before Tool Callback]
    BT --> EP[Execution Policy]
    EP -->|allow| T[TOOL]
    EP -->|block| PB[Policy Result]
    T --> TC[ToolContext]
    T --> ES[Enterprise System]
    ES --> AT[After Tool Callback]
    AT --> M
    PL[PLUGIN] -. cross-cutting observation .-> I
    PL -.-> M
    PL -.-> T
    BT --> TR[Invocation Trace]
    AT --> TR
    PL --> TR
    TR --> ER[Execution Report]
```

------------------------------------------------------------------------

## 22. ADK Concepts vs Components We Build

### ADK runtime concepts used

``` text
Agent
App
Runner
Session Service
InMemorySessionService
Session
InvocationContext
ToolContext
Callbacks
Plugins
Events
```

### Enterprise/runtime components built in this lab

``` text
RequestContext
ExecutionPolicy
InvocationTrace
Invocation Registry
Execution Report
Correlation IDs
Repeated-call detection
Failure taxonomy
Policy termination semantics
```

This distinction is important: ADK supplies the runtime framework;
application engineering adds the enterprise controls around it.

------------------------------------------------------------------------

## 23. Project Structure

``` text
project/
├── data/
├── app/
├── src/
└── tests/
```

### `data/` --- simulated enterprise systems

``` text
incidents.json
metrics.json
deployments.json
history.json
```

### `app/` --- the system being built

``` text
app/
├── agent.py
├── callbacks.py
├── enterprise/
└── harness/
```

`agent.py` defines the model, instructions, tools, callbacks, App, and
plugin registration.

`enterprise/` contains the business capabilities exposed to the agent.

`callbacks.py` contains lifecycle interception and execution-policy
enforcement.

`harness/` contains the enterprise runtime-control layer:

``` text
context.py    → trusted request metadata
policy.py     → execution limits
trace.py      → execution history and metrics
registry.py   → active invocation trace binding
plugin.py     → cross-cutting runtime observation
report.py     → final execution report
```

### `src/` --- executable learning path

``` text
00_preflight.py
01_context_and_anatomy.py
02_enterprise_runner.py
03_harness_torture_test.py
```

``` text
00 → Is the environment ready?
01 → What runtime concepts exist?
02 → Execute the complete agent runtime.
03 → Deliberately stress the harness.
```

------------------------------------------------------------------------

## 24. Recommended Reading Sequence

``` text
1. COURSE-MAP.md
       ↓
2. app/agent.py
       ↓
3. app/enterprise/tools.py
       ↓
4. src/02_enterprise_runner.py
       ↓
5. app/harness/context.py
       ↓
6. app/harness/policy.py
       ↓
7. app/harness/trace.py
       ↓
8. app/callbacks.py
       ↓
9. app/harness/plugin.py
       ↓
10. src/03_harness_torture_test.py
```

At each stage, ask:

``` text
What responsibility does this component own?
What information does it receive?
What does it produce?
Is it model-controlled or runtime-controlled?
What happens if it fails?
```

------------------------------------------------------------------------

# 25. Day-1 Mental Model

### Agent provides reasoning and capabilities

``` text
Agent = model + instructions + tools + lifecycle behavior
```

### Runner executes the agent

``` text
User Request → Runner → Agent → Model/Tools → Events
```

### Session and invocation describe different scopes

``` text
Session
├── Invocation 1
├── Invocation 2
└── Invocation 3
```

### Enterprise harness controls the execution

``` text
                 AGENT EXECUTION
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     Observe         Control        Explain
        │              │              │
      Trace          Policy         Report
     Plugin         Callbacks      Termination
```

> **The model reasons. The agent gives it capabilities. The Runner
> executes it. The session provides continuity. Context carries runtime
> information. Callbacks intercept execution. Plugins provide
> cross-cutting behavior. The enterprise harness observes, constrains,
> and explains the complete invocation.**
