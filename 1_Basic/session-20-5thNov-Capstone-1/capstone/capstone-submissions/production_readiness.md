# Production readiness (one page)

> Code paths on this page are relative to [`retail-control-tower/`](retail-control-tower/).

**Verdict:** ready as a supervised pilot for analysts on the demo data; **not** ready for production traffic. The control logic (evidence, freshness, failure handling, limits, tracing) is production-grade; hosting, identity and scale are training-grade.

| Area | Today | Ready? | To production |
|---|---|---|---|
| Correctness controls | Evidence IDs checked by the harness; freshness decided in code; postmortems labelled as hints; before/after test in code; the specialist's verdict and numbers set by code; the answer's header checked by code against the trace | ✅ | Add Check Grounding on the free-text inference |
| Failure handling | Specialist down → partial answer; stale or missing data → unknown; conflict → escalation; budgets block; fail closed without context | ✅ | Alert on partial-answer and stop-reason rates |
| Write safety | Read-only except escalations; escalation needs analyst confirmation; idempotent | ✅ | Escalations into the real case system (via MCP or its API), not a BigQuery table |
| Evaluation | 142 offline tests; 34-case golden set run on GCP with a pass/fail gate; retrieval experiments | ⚠️ no CI yet | Run tests and the eval gate in CI on every change; add adversarial cases and production samples |
| Observability | Correlation ID across both services; masked JSON logs; trace row per invocation | ⚠️ local files | Cloud Logging + Cloud Trace (OpenTelemetry), dashboards and alerts |
| Identity and access | Training sign-in (email → salted hash), not authenticated; a signed, expiring token on every API call | ❌ | IAP or the company IdP; user from the verified token; IAM per service account |
| A2A security | Plain HTTP on localhost, no auth | ❌ | HTTPS, service-to-service auth (ID tokens), security scheme on the Agent Card |
| Hosting | Two local processes | ❌ | Two Cloud Run services (min instances 1 for latency), or Agent Engine |
| Sessions | SQLite file | ⚠️ | Vertex AI sessions (already supported: `SESSION_BACKEND=vertex`) |
| Caches | JSON files under `output/cache/` | ⚠️ | Memorystore (Redis) with the same keys and TTLs |
| Data freshness | Daily synthetic load; 300-minute demo max age | ⚠️ | Live feeds (CDC or streaming into BigQuery); max age ~1 hour; freshness SLO alert |
| Documents | Register CSV, manual ingest | ⚠️ | Register owned by the document system; scheduled ingest on MD5 change |
| Privacy | Customer details never returned by tools; masking before logging | ✅ | DLP scan on logs; retention policy on sessions (30 days) |
| Cost and quota | Budgets cap calls per request; caches on embeddings and retrieval | ⚠️ | Quota increase for Gemini; per-analyst rate limit; cost per investigation metric |

**Top 3 risks**

1. **Wrong cause from an inference the checks don't cover.** Numbers and IDs are verified, the reasoning between them isn't. Mitigation: fixed format separates observation from inference; the analyst decides; the golden set grows with every reported miss.
2. **Stale or late data looks current.** Freshness is checked by source time, but carrier feeds can be hours late (S3). Mitigation: feed-lag fields in carrier results; production freshness SLOs per source.
3. **Specialist latency.** The A2A hop measured 9–15 s (5 model calls in the specialist). Mitigation: 30 s timeout with a partial answer; at scale, min instances and a smaller specialist model.

**1,000 concurrent analysts:** both services on Cloud Run with autoscaling and connection pooling; Vertex AI sessions; Memorystore caches; a BigQuery reservation or materialized views for the live tables; Gemini quota; per-user rate limits at the web tier.
