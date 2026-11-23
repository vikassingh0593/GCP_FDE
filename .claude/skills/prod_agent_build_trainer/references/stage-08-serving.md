# Stage 8: API and serving

**Goal:** a verified caller reaches only their own data, and the service stays stable under load.
**Go deeper:** concepts.md §14, §19, §23 and §26; arch.md flow 2, steps Q1–Q3, and flow 6.

## Build steps

1. Build one long-lived runtime at start-up, with one Runner and shared services.
2. Keep the API thin: validate input, resolve identity, call the runtime, shape the response.
3. Build the trusted request context at this boundary, from the verified caller.
4. Add input limits, consistent errors and health checks.
5. Add queues, rate limits and deadlines for peak load.
6. Write run instructions, and test them from a clean checkout.

**Typical serving stack:** front end → Identity-Aware Proxy → API gateway (quota, rate limit) → Cloud Run (agent host) → Vertex AI and enterprise APIs.

## Checks

### SV-01 · Blocker · Callers are authenticated (scan)
- **Look for:** identity taken from a verified token or a trusted proxy header, not from the request body.
- **Why:** an email in a form is identification, not authentication: anyone can type anyone's email and get their conversations.
- **Fix:** put IAP or Identity Platform in front, and read the verified identity on the server. Lab-only gap in a training app, and say so plainly in its UI.

### SV-02 · Blocker · IDs in the path are authorized
- **Look for:** routes like `/api/users/{user_id}/sessions` that trust the path or body.
- **Why:** changing a number in a URL shows another person's data. This is the most common API flaw, and scoping a lookup by `user_id` doesn't help if the caller supplies `user_id`.
- **Fix:** derive `user_id` from the verified caller, and reject a mismatch.

### SV-03 · High · The trusted context is built at the boundary
- **Look for:** one request context created per request, from the verified caller.
- **Why:** identity set later can be missed by a code path.
- **Fix:** build it in one place, such as a dependency or a middleware.

### SV-04 · Medium · Input is limited
- **Look for:** schema validation with length limits on every field.
- **Why:** unbounded input is a cost attack and can crash the context window.
- **Fix:** use Pydantic `Field(min_length=..., max_length=...)`.

### SV-05 · Medium · Errors don't reveal internals (scan)
- **Look for:** exception text returned to clients.
- **Why:** stack details help attackers and confuse users.
- **Fix:** log the detail, and return a stable code with the correlation ID. Acceptable in a teaching UI, as a lab-only gap.

### SV-06 · High · Every call has a timeout, and the request has a deadline (scan)
- **Look for:** timeouts on external calls and a per-request deadline.
- **Why:** one slow dependency holds a worker, and enough of those stop the whole service.
- **Fix:** bound every call, and make the sum fit inside the deadline.

### SV-07 · High · There are per-user quotas and rate limits
- **Look for:** limits in a gateway or in code.
- **Why:** one user or script can consume the shared model quota for everyone.
- **Fix:** add Apigee or API Gateway quotas, and per-user budgets.

### SV-08 · High · Bursts are absorbed, not passed on
- **Look for:** a queue, concurrency limits, priorities, deadlines and load shedding.
- **Why:** with 1,000 exceptions in two minutes and a warehouse API allowing 100 requests a minute, the model can't reason its way out. Infrastructure capacity is an engineering problem.
- **Fix:** use Pub/Sub or Cloud Tasks with workers, per-dependency rate limits, and a defined degraded mode.

### SV-09 · Medium · Start-up checks and health checks exist
- **Look for:** a working preflight, and a health endpoint. A commented-out `run_preflight()` is a warning sign.
- **Why:** a preflight that checks authentication, the model and the data turns a confusing runtime error into a clear start-up error.
- **Fix:** add a preflight with one live call per dependency. Separate "is the process up?" from "is it ready for traffic?".

### SV-10 · Medium · Configuration is explicit and safe
- **Look for:** settings read once at start, required values checked, secrets not in env files.
- **Why:** settings read at import time silently fall back to defaults if the env file wasn't loaded first, leaving an empty project.
- **Fix:** fail at start-up when a required value is missing. Secrets come from Secret Manager.

### SV-11 · Medium · CORS lists real origins (scan)
- **Look for:** `allow_origins=["*"]`.
- **Why:** any website can then call the API from a signed-in user's browser.
- **Fix:** list the real front-end origins.

### SV-12 · Medium · Run instructions work from a clean checkout
- **Look for:** instructions that name the real steps: virtual environment, install, load settings, sign in, start.
- **Why:** if a teammate can't start it, nobody can operate it. `cd /` in a run note goes to the filesystem root and gives `No module named app`.
- **Fix:** test the steps from a fresh clone.

### SV-13 · Note · Responses stream
- **Look for:** streaming for long answers.
- **Why:** 30 seconds of a blank screen feels broken.
- **Fix:** stream, and show progress.

### SV-14 · Blocker · Every submission from an agent-built UI is validated on the server
- **Look for:** the endpoint that receives form actions. Does it validate the values against a schema before doing anything? A validator module that exists but is never called; a submit handler that prints or echoes the raw values and returns success.
- **Why:** a form the agent built is model output, and the browser can send anything. Without server validation, bad or malicious values reach your systems, and printing the raw submission puts personal data in the logs.
- **Fix:** map the model's field names to one canonical schema, validate with that schema and the business rules, and return field errors (HTTP 422) to the form. Log the outcome and an ID, not the values. Test it with a bad email and an unknown field.
- **Go deeper:** concepts.md §15 (A2UI); arch.md flow 2c, step U7.

### SV-15 · High · Agent-built UI uses a pinned catalog, never HTML or script from the model
- **Look for:** the model asked to produce HTML or JavaScript; UI messages rendered without validation; client and agent using different catalog versions; `innerHTML` filled with model text without escaping.
- **Why:** HTML or script from the model is an injection path into the user's browser. A catalog limits the model to components the client knows how to render safely.
- **Fix:** send UI through the A2UI toolset with a catalog pinned to one version on both sides, so invalid messages are rejected before the screen. Escape any model text shown outside the renderer.
- **Go deeper:** concepts.md §15 (A2UI); arch.md flow 2c, steps U3–U5.

### SV-16 · Medium · The UI claims success only after code confirmed it
- **Look for:** a confirmation screen that says "validated", "submitted" or "approved" whatever the server did; an agent instruction that lets the model announce an approval.
- **Why:** the user acts on what the screen says. A false "approved" is a decision the system never made.
- **Fix:** show the confirmation only from the server's validated, stored result. Approvals come from a person or a policy in code; the agent's instruction says it never claims approval.
- **Go deeper:** arch.md flow 2c, step U8.

## Local → production

| Lab | Production |
|---|---|
| `uvicorn` on localhost | Cloud Run behind a load balancer and IAP |
| Identity from a form | Verified identity from a token or IAP |
| No limits | Gateway quotas, queues, load shedding |
| `reload` and local env file | Built image, per-environment configuration, Secret Manager |
| A UI submission printed and echoed | Validated against a schema, stored, audited, then confirmed |

## Defend it

- What is the difference between identification and authentication?
- What stops a user changing the ID in a URL?
- What happens at 10 times normal load?
- What does your service do when Gemini returns 429 for ten minutes?
- Your agent built the form, so why validate its submission again?
