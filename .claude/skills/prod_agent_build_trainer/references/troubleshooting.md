# Troubleshooting

Real errors from building agents in this course. Match the symptom, then give the cause, the fix, and the check that would have caught it.

## Start-up and environment

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| `ModuleNotFoundError: No module named 'app'` | Running from the wrong folder, or as a script from a subfolder | Run from the project root with `python -m app.server`, or set `PYTHONPATH=.` | SV-12 |
| `RefreshError: Reauthentication is needed` | The Google login (ADC) expired | `gcloud auth application-default login`, then `gcloud auth application-default set-quota-project <project>`, then restart the server | SV-09 |
| Settings are empty or use defaults, with no error | `lab.env` wasn't loaded in this terminal before Python started. Settings are read at import | `source lab.env` in the same terminal, and restart after changing it | SV-10 |
| Empty project ID in errors or URLs | Same as above | Same as above, and fail at start-up when a required value is missing | SV-10 |
| `ImportError` or missing `sqlalchemy` from `DatabaseSessionService` | Database packages aren't installed | Install SQLAlchemy, aiosqlite and greenlet | SV-12 |
| A provisioning script fails on the second run | It catches the wrong exception: the API can raise `AlreadyExists` or a 409 `Conflict` | Handle both, so a re-run creates nothing | KN-03 |
| A setup script stops right after pytest prints `no tests ran` | pytest exits with code 5 when it finds no tests, and `set -e` stops the script | Add the tests, or remove the step until they exist | EV-02 |
| `address already in use` when a server starts | Two local services use the same port, for example an MCP server and an A2A agent both on 8001 | Give each service its own port in configuration | SV-10 |
| `adk web <folder>` doesn't list your agent | `adk web` lists the sub-folders of the folder you give it, one agent each | Point it at the folder that contains the agent package, not the package itself | SV-12 |

## Agent definition

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| `Node name '...' must be a valid Python identifier` | Spaces in the agent name | Use letters, digits and underscores | AG-01 |
| `Extra inputs are not permitted` on `instructions` | The field is `instruction`, singular | Rename it | AG-01 |
| `KeyError: Context variable not found: 'user:...'` | An instruction placeholder without `?`, and the key is missing | Write `{user:name?}`, or set the key at session creation | ST-08 |
| The agent ignores a tool or picks the wrong one | The docstring is missing or vague, and the model sees only the declaration | Write a clear docstring, then print the declaration and read it | AG-02 |
| `AttributeError` containing `session_service_create_session` | A dot was typed as an underscore | `runtime.session_service.create_session(...)` | AG-01 |

## State and memory

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| A preference is "stored" but missing in a new session | State key prefix typo such as `users:` | Use `user:`, and test across two sessions | ST-01 |
| A placeholder stays blank in the prompt | The key doesn't match, or the prefix is wrong | Compare the write and the placeholder exactly | ST-01 |
| A follow-up works, but a new session knows nothing | That's correct: history is per session | Move lasting facts to `user:` state or memory | ST-02 |
| `load_memory` finds nothing | The session was never saved, or the server restarted with in-memory memory | Call `add_session_to_memory`. In-memory memory is lost on restart | ST-05 |
| `load_memory` misses an obvious fact | `InMemoryMemoryService` matches keywords, not meaning | Use the same words to test, or use Memory Bank | ST-06 |
| `AttributeError: ... save_session_to_memory` | The method is `add_session_to_memory` | Rename the call on the memory service | ST-05 |
| `ValueError: App name ... is not valid` | Vertex needs an engine ID or a full resource name | Check the app-name logic and the backend | ST-07 |
| `'NoneType' object has no attribute ...` from a service | The backend selector fell through on a typo in configuration | Raise on an unknown value | ST-13 |
| Sessions survive a restart, but memories don't | SQLite sessions with in-memory memory | Expected in a lab. Re-save, or use a durable memory service | ST-06 |

## Model and quota

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| 404 or model not found | The model is retired or the name is wrong | Move to a current model, and re-run the evaluation | AG-10 |
| 429 or 503 | Shared capacity or quota | Retry with backoff and show a busy message; consider reserved capacity | AG-11 |
| High latency with little output | Shared-capacity retries, or thinking time | Measure each step before changing anything | KN-21 |
| `model_validate_json` raises and the run crashes | Invalid structured output isn't handled | Catch it as `MODEL_DECISION_INVALID`, with bounded retries | OR-16 |

## Retrieval and answers

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| A made-up document ID still returns results | Vector search never returns empty | Route exact IDs to a lookup that can say "no such document" | KN-12 |
| Text search misses a clear paraphrase | Lexical search only | Use hybrid search | KN-12 |
| Fewer results than asked for after filtering | The filter ran after the search | Pre-filter, or store filter columns in the index | KN-11 |
| A right-looking answer has a wrong table value | A table split or misread | Keep tables whole, and add a claim-to-cell check | KN-06 |
| Zero rows from correct-looking SQL | The filter value differs from the data, like `'Rash'` and `'rash'` | Add real example values to the schema context | DB-05 |
| A search tool failed but nothing was logged | A swallowed exception | Log every tool failure with its traceback | OP-04 |
| A `KeyError` on cards that have no page | Not every evidence card has every field | Handle optional fields, and add a tool-path test | AG-05 |

## Orchestration

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| A "grounded result" appears after a budget stop | Synthesis runs whatever the end reason | Branch on the termination reason | OR-08 |
| A useful second search is blocked | Repeats are counted by action name only | Fingerprint action plus arguments | OR-05 |
| One rejection ends the whole run | Any block terminates | Record it, re-plan, and count rejections | OR-06 |
| A knowledge search returns nothing for a real symptom | The argument text doesn't match the stored key | Use an allowed vocabulary, or normalize | OR-17 |
| The same path runs for every case | A hidden router, or a prompt that dictates order | Prove adaptivity by changing one fact | OR-14 |

## MCP and A2A

| Symptom | Cause | Fix | Check |
|---|---|---|---|
| The reply is an error such as `Failed to initialize remote A2A agent: … Failed to resolve AgentCard from URL …` | The remote agent isn't running, or the card URL or port is wrong | Start the remote agent first, then open the card URL with `curl` to prove it answers | OR-20 |
| `A2A request failed: …` after earlier calls worked | The remote agent stopped after its card was loaded | Restart it, and make sure the parent reports "unavailable" instead of guessing | OR-20 |
| A delegated question hangs for minutes | `RemoteA2aAgent` waits up to 600 seconds by default | Set `timeout=` | OR-21 |
| The card loads on your machine, but other machines can't call the agent | The card advertises `to_a2a`'s `host` and `port`, which default to `localhost` | Set the public host, port and protocol, or pass your own `agent_card` | OR-23 |

## If it isn't listed

Read the traceback from the bottom up, and find the last frame in the user's own code. Then read the installed library's source at the failing line: `.venv/lib/python*/site-packages/google/adk/...`. Library behavior changes between versions, so the source beats memory. Add the new symptom here afterward (see `maintenance.md`).
