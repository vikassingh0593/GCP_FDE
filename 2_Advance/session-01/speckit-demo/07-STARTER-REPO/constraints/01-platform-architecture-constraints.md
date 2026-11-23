# ENGINEERING CONSTRAINTS — Instructor-provided, not business requirements
**Status:** Prescribed for the training exercise. Feed to `/speckit.constitution` and `/speckit.plan`, NOT blindly into `/speckit.specify`.

## Technology
- Monorepo, TypeScript end-to-end.
- React + Vite frontend; Node.js 20+ with Express backend.
- PostgreSQL for persistent storage; use a migration tool and repository abstraction.
- REST API with OpenAPI 3.1 contract.
- Local development through Docker Compose (database) and documented npm scripts.
- No external paid service required for local demo.

## Architecture
- Explicit separation of `web`, `api`, `domain`, `persistence` and `tests`.
- Controllers validate inputs and delegate to services; authorization enforced server-side.
- Use a small modular monolith; no microservices, message broker or Kubernetes.
- API contracts and database migrations must align with requirements and tasks.
- Request IDs, UTC timestamps and explicit state transitions.

## Quality
- Strict TypeScript, lint, formatting, unit and API integration tests.
- At least one negative authorization test per protected resource.
- CI runs install, typecheck, lint, tests and dependency audit (audit failures require review, not silent suppression).
- Meaningful errors, no secrets in logs, deterministic test fixtures.

## Boundaries
These are implementation constraints, not guarantees of production readiness. If the agent recommends alternate stack, record the deviation and ask for instructor approval.
