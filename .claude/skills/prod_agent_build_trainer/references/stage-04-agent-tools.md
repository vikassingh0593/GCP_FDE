# Stage 4: Agent and tools

**Goal:** an agent that uses well-defined tools, where a wrong tool choice is unhelpful but never unsafe.
**Go deeper:** concepts.md §10, §14 and §15; arch.md flow 2, steps Q7–Q9, and flow 5 for MCP.

## Build steps

1. Design each tool's contract before writing it (see the table below).
2. Write tools as plain functions with typed parameters and clear docstrings.
3. Print the declaration and read it the way the model does (`FunctionDeclaration.from_callable`).
4. Write the agent: a model, an instruction and tools.
5. Move every safety rule out of the prompt and into tools or callbacks.
6. Test tools without any model.

### Tool contract: write this for every tool

| Part | Example |
|---|---|
| Purpose, input and output schema | `check_inventory(sku)` returns on-hand, reserved, available |
| Source of truth and freshness | Inventory service; snapshot time included |
| Timeout and retry policy | 2 s; 2 retries with backoff |
| Idempotency | Safe to retry (read). A future write isn't, automatically |
| Authorization scope | Warehouses in the caller's region |
| Error contract | `NOT_FOUND`, `TIMEOUT`, `DEPENDENCY_UNAVAILABLE`… |
| Cost and rate limit | 100 requests per minute |
| Sensitive fields | Which are removed, and which are masked |
| Audit | What is recorded |

### Result shape: the same for every tool

```python
{"status": "success", "code": "OK", "data": {...}, "retryable": False}
{"status": "error", "code": "TIMEOUT", "message": "...", "retryable": True}
```

## Checks

### AG-01 · Blocker · The agent loads, and uses real ADK names (scan)
- **Look for:** the name is a valid Python identifier and isn't `user`. The field is `instruction=`, not `instructions=`. Method names are right.
- **Why:** these fail at import, so nothing runs. ADK forbids extra fields.
- **Fix:** use a name like `customer_success_agent`, and `instruction=`. Check method names in the installed ADK source.

### AG-02 · Medium · Every tool has a clear docstring (scan)
- **Look for:** a docstring saying what the tool does and when to use it, with typed parameters.
- **Why:** the model never sees your code. The docstring becomes the tool description, so without it the model chooses from a name alone. Docstrings are part of the prompt.
- **Fix:** write what it does, when to use it, and what each argument means.

### AG-03 · Blocker · Identity never comes from the model (scan)
- **Look for:** tool parameters such as `user_id`, `tenant_id`, `role`, `is_admin` or `approved`.
- **Why:** anything in a tool's parameters is chosen by the model and can be steered by a prompt. "I'm the admin" must not change anything.
- **Fix:** read identity from the trusted request context (Stage 6), and remove those parameters.

### AG-04 · High · Arguments are validated in code
- **Look for:** type, format, range and allowed-value checks inside the tool. Text the user named is checked against what they may access.
- **Why:** a schema proves the shape, not that the value is allowed.
- **Fix:** validate before fetching. Return `INVALID_ARGUMENT` on failure.

### AG-05 · High · One result contract, no raw exceptions
- **Look for:** all tools returning the same shape, with distinct error codes.
- **Why:** the runtime must tell `NOT_FOUND` from `DEPENDENCY_UNAVAILABLE` to decide between stop and retry. Raw Python exceptions aren't a business contract.
- **Fix:** catch failures in the tool, and return the normalized shape.

### AG-06 · Blocker · Read tools and action tools are separate
- **Look for:** tools that change anything sitting behind human approval, or absent from the agent.
- **Why:** a wrong guess by a read tool wastes a call. A wrong guess by an action tool changes the real world.
- **Fix:** default to read-only. For actions: propose → approve → execute, with an idempotency key, an audit record and an undo path. See concepts.md §20.

### AG-07 · Blocker · Safety rules live in code, not only in the prompt
- **Look for:** rules written only in the instruction.
- **Why:** "never show another unit's data" in a prompt doesn't stop it. A prompt is a request; code is a control.
- **Fix:** enforce it in a tool or callback. Keep the prompt line too if it helps the model behave.

### AG-08 · High · Tools return only allowlisted fields
- **Look for:** a tool building its output field by field.
- **Why:** a field the model never receives can't leak.
- **Fix:** select fields explicitly rather than returning a whole record.

### AG-09 · Medium · Instructions hold behavior, not data
- **Look for:** business facts, product names or per-turn content in the instruction.
- **Why:** hard-coded facts go stale, and per-turn content stops the prefix from being cached.
- **Fix:** keep facts in tools and configuration. Build any catalogue from the registry at start-up.

### AG-10 · High · Model names are in configuration, and not retired (scan)
- **Look for:** model IDs only in configuration, and a current model.
- **Why:** every model has a retirement date, and a retired model stops the system with a 404. A hard-coded name means a code change to fix it.
- **Fix:** keep it in configuration, track retirement dates, and re-run the evaluation before switching.

### AG-11 · High · Model errors are handled
- **Look for:** retries with backoff on 429 and 503, and a fixed fallback message.
- **Why:** shared-capacity errors are normal under load. A user should get "busy, try again", not a stack trace.
- **Fix:** configure retries, and add an `on_model_error_callback`.

### AG-12 · Medium · One model per task, chosen by evaluation
- **Look for:** separate choices for router, writer and classifier, each measured.
- **Why:** a stronger model isn't always better for a job, and cost per successful task is what matters.
- **Fix:** compare candidates on the golden set, and record the numbers.

### AG-13 · Medium · The function-calling mode fits the step
- **Look for:** `ANY` to force a tool, `NONE` for a step that must take no action.
- **Why:** `AUTO` lets the model skip a step you need.
- **Fix:** set the mode per step, or run the loop yourself when each call must be validated first.

### AG-14 · Medium · Word lists aren't used for decisions a model should make
- **Look for:** keyword patterns deciding safety cases.
- **Why:** in one real build, patterns missed 5 of 8 rewordings of a patient question, while a classifier got 22 of 22.
- **Fix:** use a classifier run by code that fails closed: "unsure" goes to a person.

### AG-15 · High · MCP tools are plain, tested functions with clear descriptions
- **Look for:** model calls inside MCP server tools; tools with no docstring or a vague one; no tests that call the functions directly.
- **Why:** an MCP server is shared by every agent that connects. Its docstrings become the descriptions those agents' models read, so a vague one causes wrong tool choices everywhere, and a bug reaches every client at once.
- **Fix:** keep business logic in plain functions that return evidence computed in code, test them without a model, and register them on the server unchanged.

### AG-16 · High · The agent sees only the MCP tools it needs, from servers you trust
- **Look for:** `McpToolset` without `tool_filter`; MCP servers that aren't on an allowlist or pinned to a version.
- **Why:** every tool a server publishes, with its description, goes into your agent's prompt. A tool the server's owner adds later appears in your agent without review, and a description can carry hidden instructions.
- **Fix:** list the allowed tools with `tool_filter`, allowlist and pin servers, and review tool descriptions like code.

### AG-17 · High · Remote endpoints come from configuration and require sign-in (scan)
- **Look for:** a literal URL in `StreamableHTTPConnectionParams(url=...)` or `RemoteA2aAgent(agent_card=...)`; remote servers that accept calls without authentication.
- **Why:** a hard-coded `localhost` works on one laptop and nowhere else, and a server without sign-in can be called by anyone who can reach it.
- **Fix:** read every URL from configuration. On Cloud Run, require IAM and send an ID token: `headers` or `header_provider` for MCP, `auth_scheme` and `auth_credential` for A2A. A hard-coded local URL is a lab-only gap.

### AG-18 · High · A declined confirmation reaches the model as "declined", not as an error
- **Look for:** what the model receives after a person declines a tool that needs confirmation (`FunctionTool(require_confirmation=True)`).
- **Why:** ADK answers the model with `{"error": "This tool call is rejected."}`. A model reads that as a failure: in one build it told the analyst "the escalation could not be saved at this time", dropped its answer format and offered to retry.
- **Fix:** an `after_tool_callback` that replaces the rejection with a plain result (declined by the user, nothing saved, not a failure, don't retry), an instruction line for that case, and a test that checks what the model sees.

### AG-19 · High · Blocking tools don't run on the event loop
- **Look for:** synchronous tools that call a database or an API inside an async server (FastAPI, an A2A server).
- **Why:** a plain function tool runs on the event loop, so one slow query stalls every other request on the process, health checks and the Agent Card included.
- **Fix:** run tools in ADK's tool thread pool (`RunConfig(tool_thread_pool_config=ToolThreadPoolConfig(...))`), or make them async and put the blocking call in `asyncio.to_thread`.

### AG-20 · High · A message that names a record gets a fresh lookup
- **Look for:** the same question about one record asked twice in a session, and whether the second answer called any tool.
- **Why:** the history is in the prompt, so the model can answer again from the earlier turn and present its stock figures and data age as current. In one build an instruction line ("a question naming an order is a new investigation") did not stop it on the live app.
- **Fix:** a `before_model_callback` that finds a record ID in the latest user message and, while that record's lookup hasn't run in this turn, sets `llm_request.config.tool_config` to function-calling mode ANY with only the lookup tool in `allowed_function_names`. ADK copies the agent's model config for each call, so the forced mode ends with that call. Test it with a scripted model.
- **Go deeper:** concepts.md §14 (fresh lookup).

## Local → production

| Lab | Production |
|---|---|
| `adk web` | Agent Engine or Cloud Run, behind sign-in |
| Action tools run directly | Action tools behind an approval step |
| Direct calls to one model | Configured models, tested fallback, cost tracking |
| MCP server on `127.0.0.1`, URL in code | MCP server on Cloud Run behind IAM, URL from configuration |
| The agent sees every tool a server publishes | `tool_filter` lists the tools this agent needs |

## Defend it

- What does the model actually see of a tool?
- What is the difference between a read tool and an action tool?
- Why isn't a rule in the prompt enough?
- What happens to your system on the day your model is retired?
- When does a capability belong on an MCP server instead of in your agent's code?
- What does your model see when a person declines its tool call?
- The user asks about the same record twice. Where does the second answer's data come from?
