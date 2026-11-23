# Research & Decisions: ServiceDesk Lite

No web research was needed: stack choices are prescribed by
`07-STARTER-REPO/constraints/01-platform-architecture-constraints.md`. These records cover the
choices that remained open inside those constraints.

## RD-01 Monorepo layout
- **Decision**: npm workspaces: `apps/web`, `apps/api`, `packages/domain`,
  `packages/persistence`, `tests`.
- **Rationale**: matches the required `web/api/domain/persistence/tests` separation without
  extra tooling.
- **Alternatives**: pnpm/Turborepo/Nx (extra tooling for a demo-sized repo).

## RD-02 Contract enforcement
- **Decision**: hand-authored `contracts/openapi.yaml` (3.1) is the source of truth;
  `express-openapi-validator` validates requests (always) and responses (tests/dev).
- **Rationale**: Constitution V; drift fails tests.
- **Alternatives**: generating the spec from code (contract becomes a by-product, not a gate).

## RD-03 Input validation
- **Decision**: zod schemas in controllers for domain-level rules, in addition to contract
  validation; shared types from `domain`.
- **Alternatives**: contract validation only (weaker domain rules, e.g. text length trimming).

## RD-04 Persistence
- **Decision**: `pg` with parameterized queries inside repository classes; `node-pg-migrate`
  for forward-only SQL migrations; two DB roles (owner for migrations, least-privilege app).
- **Rationale**: no ORM magic, makes ownership scoping explicit, enables audit grants.
- **Alternatives**: Prisma/Drizzle (acceptable; heavier fit with role-split grants).

## RD-05 Authorization
- **Decision**: central policy module in `apps/api/authz` backed by pure rules in `domain`;
  routes register an action name; unregistered routes are denied.
- **Alternatives**: per-controller checks (easy to forget, violates Constitution I).

## RD-06 Not-found vs forbidden
- **Decision**: return 404 for any request object the caller may not see; 403 only for
  role-level denial on actions with no object (for example category write).
- **Rationale**: prevents existence probing (FR-009).

## RD-07 Identity
- **Decision**: `IdentityProvider` interface; dev adapter with seeded fake users and signed
  cookie; OIDC adapter deferred. Startup guard blocks dev mode in production.
- **Alternatives**: local password store (forbidden by Constitution VII).

## RD-08 Testing
- **Decision**: Vitest for all packages; Supertest against the real Express app and a real
  PostgreSQL test database (Docker Compose); transaction-per-test or truncate between tests;
  deterministic seed fixtures.
- **Alternatives**: in-memory DB mock (hides grant/trigger behavior the audit tests need).

## RD-09 Frontend
- **Decision**: React + Vite, React Router, plain `fetch` client typed from the contract;
  responsive CSS (mobile-first). UI hides unavailable actions but never decides access.
- **Alternatives**: component libraries / state libraries (not needed for ~5 screens).

## Deferred (see plan D-01..D-09)
OIDC provider and library, production session store, claim-to-role mapping, manager
addressing, teams, audit viewer scope, retention, CI provider, priority values.
