# Production Notes

This reference is production-shaped, not a claim of production completeness.

Before a real deployment, add or validate:

- service-to-service authentication and authorization,
- tenant/customer isolation,
- PII/payment-field minimization,
- Secret Manager,
- persistent evidence/execution store,
- distributed rate limits,
- retry/backoff/jitter policies,
- durable recovery/checkpoints,
- queue/backpressure for bursts,
- Cloud Logging/Monitoring/Trace integration,
- prompt/model/policy version tracking,
- evaluation gates before promotion,
- canary and rollback,
- human approval for write operations,
- idempotency keys for side effects,
- SLOs and operational ownership.

A strong FDE should be able to map each item to a concrete failure mode.
