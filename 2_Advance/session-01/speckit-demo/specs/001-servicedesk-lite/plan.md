# Implementation Plan: ServiceDesk Lite

**Branch**: `001-servicedesk-lite` | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-servicedesk-lite/spec.md`

## Summary

An internal service-request portal: employees raise and track requests; administrators assign
agents; agents progress work; managers approve `ACCESS` requests; every state transition is
audited. Built as a small TypeScript modular monolith: React/Vite web app, Express REST API
described by an OpenAPI 3.1 contract, PostgreSQL via migrations and a repository layer.
Authorization is a central default-deny server-side policy. Release 1 uses a local-only dev
identity adapter behind an `IdentityProvider` interface; production authentication is a
corporate OIDC (Authorization Code + PKCE) adapter that is **specified as a boundary but not
built in release 1** (DR-07).

## Technical Context

**Language/Version**: TypeScript 5.x strict, Node.js 20+ (constraint 01)

**Primary Dependencies**: React + Vite (web); Express (api); `pg` + `node-pg-migrate`
(persistence); `zod` (request validation); `express-openapi-validator` (contract enforcement);
Vitest + Supertest (tests). Exact versions pinned at implementation by lockfile.

**Storage**: PostgreSQL 16 via Docker Compose; migrations are the only schema path

**Testing**: Vitest unit (domain), API integration against a real PostgreSQL test database,
contract verification against `contracts/openapi.yaml`, negative-authorization suites

**Target Platform**: Local development (Docker Compose DB + npm scripts); desktop and mobile
browsers. Production hosting is out of scope and undecided.

**Project Type**: Web application (monorepo, npm workspaces)

**Performance Goals**: None approved (spec SC items are demonstration outcomes, not SLAs)

**Constraints**: Modular monolith only; no external paid service; no secrets in repo

**Scale/Scope**: Demo scale: ~4 roles, 3 categories, 7 statuses, ~15 endpoints, ~5 screens

## Constitution Check

*GATE: pass before Phase 0; re-checked after Phase 1.*

| Principle | Plan response | Status |
|-----------|---------------|--------|
| I Default-Deny | `authorize(action, principal, resource)` policy; routes declare an action or the API refuses to start; test enumerates all routes | PASS |
| II Ownership/Role | Repository queries scoped by principal; non-visible → 404; self-approval blocked in domain | PASS |
| III Validation | zod schemas at controller boundary; parameterized SQL only; React escapes output | PASS |
| IV Auditability | `audit_log` in same transaction; app DB role has INSERT/SELECT only; tests | PASS (not tamper-proof, stated) |
| V API Contract | `contracts/openapi.yaml` is source of truth; validator in tests and dev | PASS |
| VI Negative Tests | Per-resource negative suite; matrix in quickstart | PASS |
| VII OIDC Boundary | `IdentityProvider` interface; dev adapter refuses production; OIDC adapter deferred, boundary documented | PASS with deferral (see D-01) |
| VIII Secrets/Privacy | `.env.example` placeholders; log redaction; seeded fake users only | PASS |
| Stack constraints | Matches constraint 01 exactly; no deviation | PASS |

Post-design re-check: PASS. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-servicedesk-lite/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/openapi.yaml
└── tasks.md            # created later by /speckit-tasks
```

### Source Code (repository root)

```text
apps/
├── web/                  # React + Vite; no business rules, no role trust
│   └── src/{pages,components,api,auth}
└── api/                  # Express; controllers validate and delegate
    └── src/
        ├── http/         # routes, controllers, zod schemas, error mapper, request-id
        ├── auth/         # IdentityProvider interface, dev adapter, (oidc boundary stub)
        ├── authz/        # policy.ts: roles x actions x ownership
        └── config/       # env parsing, production guards
packages/
├── domain/               # pure TS: entities, status machine, policy rules, no I/O
└── persistence/          # migrations/, repositories/, audit writer, db pool
tests/
├── api/                  # integration + negative authorization
├── contract/             # OpenAPI conformance
└── fixtures/             # deterministic seed users/requests
docker-compose.yml        # PostgreSQL only
.env.example
```

**Structure Decision**: npm workspaces monorepo with the five separations required by
constraint 01 (`web`, `api`, `domain`, `persistence`, `tests`). `domain` has no dependency on
Express or `pg`, so transition and policy rules are unit-testable in isolation.

## Authorization Design (RBAC + ownership)

Roles: `EMPLOYEE`, `AGENT`, `MANAGER`, `ADMIN` (single role per user until OQ-04).

| Action | EMPLOYEE | AGENT | MANAGER | ADMIN | Object condition |
|--------|----------|-------|---------|-------|------------------|
| request:create | ✔ | ✔ | ✔ | ✔ | owner = caller |
| request:read | own | assigned | addressed approvals | all | scoped in query |
| request:history | own | assigned | addressed | all | same as read |
| request:approve / reject | – | – | ✔ | – | status PENDING_APPROVAL, caller ≠ owner, addressed to caller (D-04) |
| request:assign | – | – | – | ✔ | status OPEN |
| request:start (OPEN→IN_PROGRESS), resolve (→RESOLVED) | – | ✔ | – | – | caller = assignee |
| request:close (RESOLVED→CLOSED) | owner | – | – | – | caller = owner |
| category:read | ✔ | ✔ | ✔ | ✔ | active only for create form |
| category:write | – | – | – | ✔ | – |
| user:role-write | – | – | – | ✔ | – |
| audit:read | – | – | – | ✔ (interim, OQ-11) | – |

Rules: any action not in this table is denied. Managers hold no blanket read access. Not
visible or not found both return 404 with the same body (decided once, contract-documented).
Identity and role come only from the server-side session; the frontend hides controls for
usability only.

## Status Machine (decided transitions only, FR-027)

`create` (ACCESS) → `PENDING_APPROVAL`; `create` (other) → `OPEN`; `PENDING_APPROVAL` →
`OPEN` | `REJECTED`; `OPEN` → `IN_PROGRESS`; `IN_PROGRESS` → `RESOLVED`; `RESOLVED` →
`CLOSED`. Everything else is rejected with 409. `SUBMITTED` is recorded as the creation event
and immediately followed by the routed status in the same transaction (interim, OQ-05).
No edit, cancel, reopen (OQ-03, OQ-05).

## Audit Events

Written in the same DB transaction as the change: `REQUEST_SUBMITTED`, `REQUEST_ROUTED`,
`APPROVAL_APPROVED`, `APPROVAL_REJECTED`, `AGENT_ASSIGNED`, `STATUS_IN_PROGRESS`,
`STATUS_RESOLVED`, `STATUS_CLOSED`, `CATEGORY_CREATED|UPDATED|DEACTIVATED`, `ROLE_CHANGED`,
`AUTH_DENIED` (authorization denial, no PII). Fields: id, actor_id, action, target_type,
target_id (request ID where applicable), request_id (HTTP correlation), occurred_at (UTC),
metadata (JSON, no PII/secrets). Protection: app DB role granted INSERT and SELECT only on
`audit_log`, plus a trigger raising on UPDATE/DELETE; migrations run under a separate owner
role. This is application/DB-level and **not tamper-proof**.

## Identity Boundary

- `IdentityProvider` interface: `authenticate(req) → Principal | null`, where `Principal =
  {userId, role}` is resolved server-side from the `users` table.
- **Dev adapter** (`AUTH_MODE=dev`): `POST /dev/session` picks a seeded fake user and issues
  a signed HttpOnly cookie. Config loader throws at startup if `AUTH_MODE=dev` and
  `NODE_ENV=production`; the dev routes are only mounted when dev mode is active; a test
  proves both.
- **OIDC adapter** (`AUTH_MODE=oidc`): Authorization Code + PKCE; validates issuer, audience,
  expiry, nonce; maps IdP subject to `users`. **Not implemented in release 1**; selecting it
  yields a startup error "not implemented". Provider, library, role mapping: D-01..D-03.
- Sessions: HttpOnly, SameSite=Lax, Secure outside local dev; no tokens in localStorage; CSRF
  via required custom header plus SameSite on state-changing requests.

## Risks

| ID | Risk | Mitigation |
|----|------|------------|
| R-01 | Dev identity leaks to production | startup guard, route unmounting, test |
| R-02 | Forgotten authorization on a new route | deny-by-default registry + route-enumeration test |
| R-03 | IDOR through list/filter endpoints | principal-scoped repository methods only |
| R-04 | Audit log believed tamper-proof | doc wording, DB grants, explicit non-claim |
| R-05 | Open questions (OQ-03/05/06/07/10/11) change data model | interim choices flagged D-04..D-08; revisit before tasks |
| R-06 | Contract drift | validator middleware + contract tests in CI |
| R-07 | Dependency vulnerabilities | lockfile, CI `npm audit` with recorded review |

## Unresolved Technical Decisions

| ID | Decision | Interim position |
|----|----------|------------------|
| D-01 | Production OIDC provider and client library | undecided; boundary only |
| D-02 | Session store for production (stateless signed cookie vs server store) | dev uses signed cookie |
| D-03 | Mapping IdP claims/groups to roles | undecided |
| D-04 | How a manager is "addressed" (OQ-06) | interim: any MANAGER who is not the owner; revisit |
| D-05 | Teams in data model (OQ-07) | no teams table in release 1 |
| D-06 | Who reads audit (OQ-11) | ADMIN only |
| D-07 | Retention/deletion (OQ-10) | none implemented; documented as open |
| D-08 | Priority values | `LOW`, `MEDIUM`, `HIGH` placeholder, not stakeholder-approved |
| D-09 | CI provider | not selected; commands defined as npm scripts |

## Complexity Tracking

No constitution violations; section intentionally empty.
