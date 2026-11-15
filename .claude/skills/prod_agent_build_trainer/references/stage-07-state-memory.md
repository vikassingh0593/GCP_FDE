# Stage 7: State and memory

**Goal:** each fact sits in the right store, and survives exactly what it should survive.
**Skip if:** every question is standalone and nothing carries over. Follow-up questions need at least session history.
**Go deeper:** concepts.md §14; arch.md flow 2b (session, state and memory).

## Where each fact belongs

| Store | Key | Lasts for | Example |
|---|---|---|---|
| Session history | Automatic | One conversation | The messages so far |
| Session state | No prefix: `current_case` | One conversation | The topic of this chat |
| User state | `user:` | All of that user's sessions | `user:preferred_region` |
| App state | `app:` | Everyone in the app | `app:lab_topic` |
| Temp state | `temp:` | The current invocation, never saved | `temp:last_state_tool` |
| Long-term memory | Memory service | Long term, searched when needed | "Q4 migration codename was Blue Lantern" |

**State vs memory:** state goes into the prompt automatically through placeholders. Memory doesn't: the agent has to search for it with `load_memory`, and it finds only what was saved.

## How it flows

```text
Email → stable user_id → create or pick a session (starting state)
      → Runner loads the session → placeholders filled from state → Gemini
      → tools write through tool_context.state → session service saves events and state
      → add_session_to_memory (only when your code calls it)
      → a later session finds it with load_memory
```

**Typical file layout:** `config.py` (settings), `identity.py` (who), `services.py` (where data lives), `tools.py`, `agent.py`, `runtime.py` (how it runs), `api.py`, `server.py`.

## Local → production

| Part | Lab | Production |
|---|---|---|
| Sessions | `InMemorySessionService`, or `DatabaseSessionService` on SQLite | `VertexAiSessionService`, or `DatabaseSessionService` on Cloud SQL or AlloyDB |
| Memory | `InMemoryMemoryService`: keyword match, lost on restart | `VertexAiMemoryBankService` |
| Identity | Email hashed into a stable ID, no sign-in | Verified identity (IAP), mapped to a stable ID |

Moving between them should be a configuration change. If it needs code changes in the agent, the design is wrong.

## Checks

### ST-01 · Blocker · State keys use real ADK prefixes (scan)
- **Look for:** `user:`, `app:`, `temp:`, or no prefix. A typo such as `users:` looks fine and fails silently.
- **Why:** ADK treats an unknown prefix as plain session state. The tool still returns "stored", but the value never reaches a new session, and the `{user:...}` placeholder stays blank.
- **Fix:** correct the prefix. Prove it with a test that reads the value from a second session.

### ST-02 · High · Each fact is in the right store
- **Look for:** session facts kept as user state, or lasting preferences kept in session state.
- **Why:** a case topic in `user:` state leaks one customer's case into the next conversation. A preference in session state vanishes.
- **Fix:** ask "how long should this live, and who should see it?" Use the table above.

### ST-03 · High · The user ID is stable and contains no personal data
- **Look for:** a normalized identity with a salted hash, so the same person always gets the same ID.
- **Why:** an unstable ID loses a user's history. A raw email in an ID spreads personal data into every log.
- **Fix:** normalize, then hash with a salt from configuration.

### ST-04 · High · Production sessions survive restarts and multiple instances (scan)
- **Look for:** which backend production uses.
- **Why:** `InMemorySessionService` loses everything on restart, isn't shared between instances, and isn't suitable for multi-threaded production.
- **Fix:** use a persistent session service, selected by configuration.

### ST-05 · Blocker · Memory is saved with the real method, at a deliberate moment (scan)
- **Look for:** `memory_service.add_session_to_memory(session)`, and when it runs. `save_session_to_memory` doesn't exist on ADK memory services.
- **Why:** nothing saves to memory automatically. If your code never calls it, `load_memory` finds nothing, and the agent honestly says it doesn't remember.
- **Fix:** decide when to save (end of conversation, or a user action), and call the real method on a freshly loaded session.

### ST-06 · High · Production memory is durable and searches by meaning (scan)
- **Look for:** which memory backend production uses.
- **Why:** `InMemoryMemoryService` is for prototypes. It matches keywords, so "code name" won't find "codename", and it empties on restart while SQLite sessions survive, which is confusing to debug.
- **Fix:** use a managed memory service in production.

### ST-07 · High · The app name matches the session backend
- **Look for:** logic that picks the app name. Vertex needs a numeric engine ID or a full `projects/.../reasoningEngines/<id>` name, unless the service was given an engine ID. Local backends take a plain name.
- **Why:** swapped logic gives Vertex a plain name, which raises `ValueError` on first use. Locally, it quietly stores a long name that ends in `reasoningEngines/` with no ID.
- **Fix:** return the plain name unless the backend is Vertex, and test both branches.

### ST-08 · Medium · Instruction placeholders are safe (scan)
- **Look for:** `{user:name?}` with a `?` wherever the value may be missing.
- **Why:** a placeholder without `?` raises `KeyError` when the key is missing, which is every new user's first message.
- **Fix:** add the `?`, or always set the key at session creation.

### ST-09 · High · One active request per session
- **Look for:** a disabled send button, or a lock or queue per session.
- **Why:** two overlapping turns can read the same history and save conflicting state. Different sessions can run in parallel.
- **Fix:** lock or queue per session on the server. A disabled button alone isn't enough, because two tabs can bypass it.

### ST-10 · High · Session access is scoped to the owner
- **Look for:** every lookup using both `user_id` and `session_id`, where `user_id` comes from the verified caller.
- **Why:** session IDs leak through URLs and logs. A lookup by ID alone lets anyone who has an ID read another person's conversation.
- **Fix:** always scope it, and return 404 when it doesn't match.

### ST-11 · Medium · The agent can't claim a memory it didn't retrieve
- **Look for:** an instruction rule, plus a test asking about something that was never saved.
- **Why:** a model will happily "remember" a confident invention.
- **Fix:** add the rule, and add the test to the golden set.

### ST-12 · High · Long-term memory is governed
- **Look for:** what is stored, for how long, how it is deleted, and an allowlist for writes.
- **Why:** remembered personal data needs retention and deletion like any other, and an old remembered answer can be out of date. Prompt-injected "remember this" is an attack path.
- **Fix:** use an allowlist of preference names, as a tool does with `_ALLOWED_PREFERENCES`. Treat memory as a hint, and take current facts from the source of truth.

### ST-13 · Medium · Unknown configuration fails loudly (scan)
- **Look for:** a backend selector that falls off the end and returns `None`.
- **Why:** a typo in `SESSION_BACKEND` becomes a confusing `NoneType` error far from the cause.
- **Fix:** end with `raise ValueError(f"Unknown SESSION_BACKEND: {backend}")`.

### ST-14 · Medium · Services are built once per process
- **Look for:** one `Runner`, session service and memory service created at start-up and shared.
- **Why:** creating them per request throws away `InMemoryMemoryService` contents and wastes database connections.
- **Fix:** build them once, in a runtime object.

### ST-15 · Medium · Sensitive state is masked at the boundary
- **Look for:** state returned to a browser with personal fields masked.
- **Why:** an inspector or debug endpoint is a common leak. State is stored as written, so masking belongs in code at the boundary.
- **Fix:** add a `safe_state` function, and mask fields such as `user:email`.

### ST-16 · Medium · Scope behavior is proved by a test
- **Look for:** a test showing Session B sees `user:` state but not Session A's `current_case`, and `temp:` isn't saved.
- **Why:** these bugs are silent. Reading the code isn't enough, as the `users:` typo shows.
- **Fix:** write the two-session test. It needs no model call.

## Defend it

- Why did a follow-up question work in this session, but fail in a new one?
- What is the difference between state and memory?
- Why does a saved preference appear in the prompt, while a saved fact doesn't?
- Which of your facts would be lost on a restart today?
- What stops one user reading another's session?
