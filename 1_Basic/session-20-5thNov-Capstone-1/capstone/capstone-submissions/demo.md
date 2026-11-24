# 5-minute demo

> Code paths on this page are relative to [`retail-control-tower/`](retail-control-tower/).

**Recording:** *(add the link after recording)*

## Before the demo (10 minutes earlier)

```bash
cd retail-control-tower
source .venv/bin/activate && source lab.env
python data/generate_data.py && python -m scripts.load_data      # fresh times; valid ~4 h 50 min
python -m fulfilment_specialist.server                           # terminal 1
python -m web.server                                             # terminal 2
python -m scripts.check_gcp                                      # terminal 3: must print READY
```

Open http://127.0.0.1:8080, sign in as `asha@example.com`, start a new investigation. Keep terminal 1 visible.

## Script

| Time | Show | Say |
|---|---|---|
| 0:00–0:30 | The page, the badges (model, specialist up) | "An analyst asks why an order is late. Two agents: an orchestrator I own and a Fulfilment Specialist another team owns, over A2A." |
| 0:30–1:30 | **Investigate ORD-78421.** Point at OUTCOME / CAUSE / FULFILABLE, the evidence IDs, the inspector (tools, A2A call, retrieval) | "Every fact has an evidence ID, and the harness checks each one came from a tool. Stock came from the specialist: 7 available against 40, with the snapshot time. The runbook says a re-route needs approval." |
| 1:30–2:30 | **ORD-78470 looks like the Bangalore sync incident from March. Is it the same problem?** | "The postmortem is a close match, and it's wrong. The snapshot is 10 minutes old, so sync works; 58 of 60 units are reserved by ORD-78471. Similarity is a hint, never the cause." |
| 2:30–3:15 | **Stop terminal 1** (Ctrl+C). Ask **Investigate ORD-78450.** | "The specialist is down. The answer is partial: CHG-2311 and the before/after pattern are still there, fulfilment is marked unavailable, and no stock number is guessed. If the model still writes a cause or a stronger outcome, the answer guard corrects it in code, and the CHECKED BY CODE line shows what it changed." Restart terminal 1. |
| 3:15–4:00 | **ORD-78465 says shipped. Is it on its way?** → escalation draft → **Decline**, then ask again and **Confirm** | "Order and carrier disagree, so it doesn't pick a side. The only write in the system waits for my confirmation." |
| 4:00–4:30 | Second tab, sign in as `ravi@example.com`, ask **What was the cause for the order we just looked at?** | "Another analyst's session knows nothing: it asks which order." |
| 4:30–5:00 | Copy a correlation ID, run `grep <id> output/logs/*.jsonl` | "One ID through the web app, the orchestrator, A2A and the specialist's inventory read. No customer details in any log." |

## If something goes wrong

- **Answers say "stale" everywhere:** the data is older than 300 minutes. Re-run the two commands in "Before the demo".
- **"Fulfilment check unavailable" when the specialist should be up:** check terminal 1 and `curl -s "$FULFILMENT_AGENT_CARD_URL"`.
- **429 errors:** wait a minute; the clients retry with backoff.
- **A "CHECKED BY CODE:" line in an answer:** expected. The answer guard changed a header value the evidence didn't support; the line says what and why.
- **The first question is slow:** the first search in a process takes ~4 s (clients, register read), and the A2A call 9–15 s. A full investigation takes 10–30 s. After 105 s the request stops with a partial answer.
- **"Sign in again":** the analyst token lasts 12 hours, and restarting the web app with a new `IDENTITY_SALT` invalidates it.
