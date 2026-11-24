# Stage 5: Orchestration

**Goal:** the path adapts to the evidence, while software decides what may actually run.
**Go deeper:** concepts.md §15 and §18; arch.md flow 2, flow 2a (semantic orchestration loop), flow 5 (MCP and A2A).

## Choose the pattern

| Pattern | How it works | Use it when |
|---|---|---|
| **Agent-led** | An ADK `LlmAgent` picks tools from its instruction and docstrings; callbacks guard each step | One question needs one or a few capabilities, such as a RAG assistant that routes between search, SQL and hand-off |
| **Code-led semantic loop** | Your code runs the loop. Gemini returns one structured decision per step; a policy gate approves it | Multi-step investigations where the next step depends on what was just found, and every decision must be recorded |
| **Fixed workflow** | Steps run in a set order with no model deciding (ADK Sequential, Parallel, Loop agents) | The path is always the same |

Use a model only where judgment is needed. A fixed workflow forces every case through the same steps. An unrestricted agent over-investigates, repeats expensive calls and acts beyond its authority. A semantic loop is the middle ground.

## The semantic loop

```text
Objective + trusted context
        ↓
Evidence register ◄───────────────┐
        ↓                         │
Gemini proposes ONE next action   │
        ↓                         │
Schema validation                 │
        ↓                         │
Policy gate ──reject──► visible, bounded re-plan
        ↓ allow                   │
Execute ONE action                │
        ↓                         │
Normalize the result ─────────────┘
        ↓ when policy allows ending
Grounded synthesis, or an explicit stop
```

**Keep concerns in separate files:** `contracts.py`, `policy.py`, `evidence.py`, `tools.py`, `executor.py`, `trace.py`, `synthesis.py`, `orchestrator.py`. Names may differ; separation may not.

### The decision contract

```python
class Action(str, Enum):
    GET_ORDER = "GET_ORDER"
    CHECK_INVENTORY = "CHECK_INVENTORY"
    SYNTHESIZE = "SYNTHESIZE"
    STOP_INSUFFICIENT_EVIDENCE = "STOP_INSUFFICIENT_EVIDENCE"
    ESCALATE = "ESCALATE"

class NextAction(BaseModel):
    next_action: Action          # an enum, so an invented action fails validation
    reason: str = Field(min_length=1)
    evidence_used: list[str] = Field(default_factory=list)
    expected_information_gain: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    stop_ready: bool = False
```

### Terminal states: every run ends in one of these

`SYNTHESIZE` · `STOP_INSUFFICIENT_EVIDENCE` · `ESCALATE` · `POLICY_TERMINATION` · `BUDGET_TERMINATION` · `FAILURE_TERMINATION` · `TIMEOUT_TERMINATION`

### Result states: not just success or failure

`RESOLVED` · `PROBABLE_CAUSE` · `INSUFFICIENT_EVIDENCE` · `DEPENDENCY_DEGRADED` · `CONFLICT_REQUIRES_REVIEW` · `POLICY_TERMINATED` · `ESCALATED`

## Checks

### OR-01 · Blocker · The model returns one validated decision
- **Look for:** a response schema with an enum of allowed actions, validated before anything runs.
- **Why:** prose like "checking inventory might help" can't be controlled. An enum means `DELETE_ORDER` fails validation.
- **Fix:** use `response_schema` plus `model_validate_json`.

### OR-02 · Blocker · A deterministic policy gate runs before execution
- **Look for:** code outside the model that approves each decision against the allowlist, authorization, budgets and evidence rules.
- **Why:** policy inside the model is a suggestion. A prompt can't constrain a model that has been persuaded otherwise.
- **Fix:** every decision passes the gate, and only an approved action runs.

### OR-03 · High · One approved action per step, in a loop you own
- **Look for:** one execution per decision, inside a bounded loop in your code.
- **Why:** the model must not own an unbounded loop outside runtime control. One step at a time means each decision uses the newest evidence.
- **Fix:** bound the loop, and re-plan after every action.

### OR-04 · Blocker · The model can't choose its target
- **Look for:** arguments from the model reaching a tool unchecked, especially IDs. For example `args.setdefault("ticket_id", ticket_id)` keeps whatever the model sent.
- **Why:** the model can then investigate another customer's record, and "setdefault" reads as if it were safe.
- **Fix:** overwrite targets from the trusted request: `args["ticket_id"] = ticket_id`.

### OR-05 · High · Repeats and no-progress are detected on action and arguments
- **Look for:** a fingerprint of tool name plus normalized arguments, and detection of steps that add no new evidence.
- **Why:** counting action names alone blocks a useful re-check and misses a real loop. Searching knowledge twice for two different symptoms is fine; the same symptom twice isn't.
- **Fix:** fingerprint with sorted, normalized arguments.

### OR-06 · High · A rejected proposal is visible and bounded
- **Look for:** what happens after a rejection. Is it recorded? Can the model re-plan? Is there a limit?
- **Why:** ending the run on the first rejection discards good evidence, while unlimited re-planning is a loop.
- **Fix:** record the rejection, let the model see it and re-plan, and count rejections toward a limit.

### OR-07 · Blocker · Synthesis has a deterministic gate
- **Look for:** code that rejects SYNTHESIZE until minimum evidence exists, such as an authoritative record, a cause-specific source, and no unresolved conflict.
- **Why:** confidence isn't evidence. A model can be 95% sure after one call.
- **Fix:** write the minimum evidence as a rule. Higher-risk conclusions can require more.

### OR-08 · Blocker · Running out of budget never looks like success
- **Look for:** what happens after the loop ends. Does anything call synthesis whatever the reason? A runner that always prints a "grounded result" is the classic mistake.
- **Why:** a policy or budget stop followed by a confident answer tells the customer the investigation finished when it didn't.
- **Fix:** branch on the termination reason. Only a permitted synthesis produces a conclusion; everything else reports incomplete work and what is missing.

### OR-09 · High · Evidence lives in a register
- **Look for:** evidence objects with ID, source action, source system, observed time, source time, status, freshness and correlation ID.
- **Why:** concatenated tool output can't answer where a fact came from or how old it was. One giant prompt is the first failure pattern.
- **Fix:** add an evidence object for every result. Failed calls are evidence too.

### OR-10 · High · Freshness is enforced by code
- **Look for:** a maximum age per evidence type, checked at read time.
- **Why:** a four-hour-old inventory snapshot isn't current truth, however confident the model sounds.
- **Fix:** mark stale evidence `STALE_EVIDENCE`. Decide whether to re-check, degrade or escalate.

### OR-11 · High · Conflicts are surfaced, not resolved by luck
- **Look for:** a rule using source authority, freshness and known lag. Unresolved conflicts appear in the result.
- **Why:** choosing the last value seen is a silent coin flip.
- **Fix:** write the conflict policy, and escalate critical conflicts.

### OR-12 · High · The conclusion cites evidence and separates fact from inference
- **Look for:** evidence IDs in the result, with fact, inference, hypothesis and recommendation kept distinct.
- **Why:** a similar past incident can guide the search, but it doesn't prove today's cause. Correlation isn't causation.
- **Fix:** use a structured outcome with supporting, contradictory and missing evidence. Check that every cited ID exists.

### OR-13 · High · Escalation is a normal outcome
- **Look for:** a code path where the result goes to a person, with rules, failing closed.
- **Why:** "I can't safely determine the next action" is a valid production result.
- **Fix:** add ESCALATE as an allowed terminal action, and write the conditions in code.

### OR-14 · Medium · There is no hidden hard-coded router
- **Look for:** `if payment_hold: call_payment()` style routing presented as semantic.
- **Why:** then the model adds cost and nothing else.
- **Fix:** prove it: change one fact in the evidence, re-run, and show a different next action while policy stays unchanged.

### OR-15 · Medium · Limits are configuration
- **Look for:** budgets and thresholds in one place.
- **Why:** scattered magic numbers can't be reviewed or rolled back.
- **Fix:** load them into a frozen policy object.

### OR-16 · High · Model output failures are handled
- **Look for:** what happens when validation fails or the model times out. An unguarded `model_validate_json` crashes the whole run.
- **Why:** invalid output, quota errors and safety refusals are normal in production.
- **Fix:** catch them as `MODEL_DECISION_INVALID`, retry a bounded number of times, then terminate explicitly.

### OR-17 · Medium · Free-text arguments have an allowed vocabulary
- **Look for:** arguments the model writes that must match stored keys. A knowledge base keyed `credential_warning` never matches "credential warning".
- **Why:** the search returns nothing, and the model concludes that no guidance exists.
- **Fix:** use an enum, or normalize the value in code.

### OR-18 · Medium · Specialists are used deliberately
- **Look for:** `AgentTool` when the root must stay the only voice; `sub_agents` when the conversation really moves.
- **Why:** a transfer hands the user to another agent. An `AgentTool` is called like a function, so checks still run.
- **Fix:** default to `AgentTool` for specialist work, and keep the first agent as the router.

### OR-19 · Medium · A remote agent is used only where its own reasoning is needed
- **Look for:** an A2A specialist that wraps one fixed lookup; deterministic checks sent to a model.
- **Why:** every hop adds a model call, latency, cost and a failure point, and the result comes back as text instead of exact fields.
- **Fix:** a fixed lookup stays a function tool or an MCP tool. Delegate over A2A when the work needs its own reasoning, data access, owning team or release cycle.

### OR-20 · Blocker · The answer stays safe when a remote agent is down
- **Look for:** no test with the remote agent stopped; a parent instruction with no rule for an unavailable specialist; a parent that must report partial evidence but delegates through `sub_agents`, where the remote agent takes over the turn.
- **Why:** a remote agent has its own lifecycle, so it will sometimes be down. ADK reports an unreachable remote agent as an event carrying an error message ("Failed to initialize remote A2A agent: …"), not as an exception, so nothing crashes and the failure is easy to miss. A model can then fill the gap with invented facts.
- **Fix:** stop the remote agent and test what the user sees. Instruct the parent to say the specialist is unavailable, return the evidence it has marked partial, and never supply the specialist's facts itself. When the parent must reason about the failure, wrap the remote agent in `AgentTool`: ADK returns the error message to the parent as the tool result.

### OR-21 · High · Remote calls have a deadline (scan)
- **Look for:** `RemoteA2aAgent` without `timeout=`; MCP connections left at the 300-second `sse_read_timeout` for tools that should answer in seconds.
- **Why:** `RemoteA2aAgent` waits up to 600 seconds by default, so one hung specialist holds the user's request for ten minutes.
- **Fix:** set the timeout from the request's latency budget, and treat a timeout as "unavailable" (OR-20).

### OR-22 · Medium · One correlation ID follows the request across agents
- **Look for:** logs on each side with no shared ID; no `a2a_request_meta_provider` on `RemoteA2aAgent`, no `header_provider` on `McpToolset`.
- **Why:** a wrong answer can't be traced from the orchestrator through the specialist to the tool that produced the fact.
- **Fix:** pass the correlation ID in A2A request metadata and MCP headers, and have each side log it.

### OR-23 · Medium · The Agent Card is reviewed before others can reach it
- **Look for:** `to_a2a(agent)` serving the generated card from a deployed service; `host` and `port` left at local values.
- **Why:** the card is served without sign-in. ADK builds it from the agent's description and lists each tool's name and description as a skill; it never includes the instruction. The card's URL comes from `to_a2a`'s `host` and `port` (default `localhost:8000`), so a deployed agent that keeps them advertises an address no one else can reach.
- **Fix:** pass a reviewed `agent_card` to `to_a2a`, with the public URL and only the skills callers need.

### OR-24 · Medium · Every agent owns a decision a tool can't make
- **Look for:** the agent count and each agent's job. An "agent" that only retrieves, looks something up or formats output; a topology chosen because more agents look impressive.
- **Why:** each agent adds a model call, latency, cost, a prompt to maintain and a failure point. An agent that doesn't decide anything is a slower, less predictable tool.
- **Fix:** for each agent, name the decision it owns and why a tool can't make it: it needs reasoning, has its own context or security boundary, belongs to another team or release cycle, and can fail with a safe fallback. Turn the rest into tools.
- **Go deeper:** concepts.md §18 (agent or tool).

### OR-25 · High · Decision fields the user acts on are checked by code against the trace
- **Look for:** code between the model's answer and the user that checks structured fields (outcome, cause, can it ship) against the tool results of this run.
- **Why:** these are the values a person acts on. Without a check, a model names a cause it has no proof for, or says stock is there when the stock check failed, and the answer still reads well.
- **Fix:** an answer guard: each value needs its proof in the trace, otherwise it is replaced with the safe value (`none`, `unknown`, `partial`) and a visible line says what code changed and why. Log each correction.

### OR-26 · High · A remote agent's verdict and numbers are written by its code
- **Look for:** where the specialist's reply fields (verdict, quantities, evidence IDs) come from.
- **Why:** if the specialist's model copies them from its tool results, it can copy them wrong or contradict its own tool, and the caller then treats a wrong number as checked evidence.
- **Fix:** compute the decision fields in code from the specialist's tool results (e.g. a `before_tool_callback` that overwrites them in the structured reply); the model writes only the prose. The caller still checks the reply's evidence IDs.

### OR-27 · Medium · Evidence a known step always needs is fetched by code
- **Look for:** a step that always needs the same supporting document, but where finding it depends on the model's search wording.
- **Why:** a model's query wording drifts between runs, even at temperature 0. In one build the right cause was named, but the change-incident runbook (who decides a rollback) was missed because the model reworded its search.
- **Fix:** have the tool fetch it, through the same retrieval path (register, version filter, cache), by metadata tags such as document type and exception type, never by document ID.

## Local → production

| Lab | Production |
|---|---|
| Evidence in memory, lost on crash | Persistent evidence and execution store, with a checkpoint boundary |
| One process | Queue and workers, per-order isolation, rate limits |
| Printed trajectory | Structured trace in Cloud Logging and BigQuery |
| Remote agent on `localhost`, card URL in code | Remote agent on Cloud Run or Agent Engine behind IAM; card URLs from configuration, with an allowlist |
| A remote call waits up to 600 s | A timeout from the latency budget; "unavailable" is a normal result |

## Defend it

- Why is this neither a fixed workflow nor an autonomous agent?
- Why one action per loop?
- Why can Gemini propose STOP while software still rejects it?
- What if confidence is high but evidence is weak?
- How do you stop a historical similarity becoming a false cause?
- What changes the moment the system may write?
- Why is this specialist an agent and not a tool?
- What does the user see when the specialist is down?
- Which fields in your answer does code check before the user sees them?
