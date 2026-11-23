---

description: "Task list for ServiceDesk Lite release 1"
---

# Tasks: ServiceDesk Lite

**Input**: Design documents from `/specs/001-servicedesk-lite/`

**Prerequisites**: plan.md, spec.md, data-model.md, contracts/openapi.yaml, research.md, quickstart.md

**Tests**: REQUIRED. Constitution VI mandates positive and negative tests; tasks marked **NEG** are explicit negative authorization/security tests. Test tasks come before the implementation they cover (write, see fail, then implement).

**Organization**: Grouped by user story. Paths follow plan.md (`apps/web`, `apps/api`, `packages/domain`, `packages/persistence`, `tests`).

## Format: `- [ ] T### [P?] [US?] Description (path) — AC: acceptance criteria`

- **[P]**: parallelizable (different files, no dependency on an incomplete task)
- **[USn]**: user story from spec.md (US1 submit, US2 track own, US3 agent work, US4 approval, US5 admin, US6 audit)
- **NEG**: negative test (expected refusal/failure)
- **Status of all tasks**: not started. A checked box means the task's own AC was met with evidence.

## Open items that constrain these tasks (not decided; do not invent)

- OQ-03 (edit/cancel), OQ-05 (extra transitions), OQ-06 (manager addressing; interim D-04), OQ-07 (teams), OQ-10 (retention), OQ-11 (audit viewers; interim admin only), D-01..D-03 (production OIDC) have **no implementation tasks**. Tasks implement only the decided behavior in spec.md FR-027 and the interim choices flagged in plan.md.
- `checklists/security-audit.md` findings (CHK003, 023, 026, 027, 028) are unresolved requirement gaps; T001 below records a go/no-go review before Phase 2.

---

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Review `checklists/security-audit.md` findings with the reviewer and record decisions (or accepted deferrals) at the end of that file (specs/001-servicedesk-lite/checklists/security-audit.md) — AC: each Observation item has a recorded decision or "deferred, owner, trigger"; no spec change is made silently.
- [ ] T002 Create npm-workspaces monorepo skeleton: root `package.json` (workspaces `apps/*`, `packages/*`, `tests`), `tsconfig.base.json` strict, directories per plan (package.json, tsconfig.base.json, apps/, packages/, tests/) — AC: `npm install` succeeds and creates a committed lockfile; `npm run typecheck` passes on empty packages.
- [ ] T003 [P] Configure ESLint and Prettier with scripts `lint`, `format:check` (eslint.config.js, .prettierrc) — AC: `npm run lint` passes on the skeleton; a deliberate lint error fails it.
- [ ] T004 [P] Create `docker-compose.yml` with PostgreSQL 16 only, plus `.env.example` containing placeholders only (docker-compose.yml, .env.example, .gitignore) — AC: `docker compose up -d db` yields a reachable database; `.env` is git-ignored; `.env.example` has no real secrets.
- [ ] T005 [P] Add test tooling: Vitest config, Supertest, shared setup that connects to the test database (tests/vitest.config.ts, tests/setup.ts) — AC: a trivial test runs via `npm test`.
- [ ] T006 Add `scripts/ci.sh` and root script `npm run ci` running install, typecheck, lint, test, test:contract, `npm audit` (scripts/ci.sh, package.json) — AC: script exits non-zero when any step fails; audit failure is reported, not suppressed (CI provider undecided, D-09).

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work starts until this phase is complete.

### Domain (pure, no I/O)

- [ ] T007 [P] Define roles, statuses, priorities and error types in `packages/domain/src/{roles,status,priority,errors}.ts` — AC: enums equal the contract exactly: Role `EMPLOYEE|AGENT|MANAGER|ADMIN`; Status `SUBMITTED|PENDING_APPROVAL|OPEN|IN_PROGRESS|RESOLVED|CLOSED|REJECTED`; Priority `LOW|MEDIUM|HIGH` (placeholder D-08).
- [ ] T008 [P] Write unit tests for the transition table before implementing it (tests/unit/domain/transitions.test.ts) — AC: tests cover each decided transition (`PENDING_APPROVAL`→`OPEN`/`REJECTED`, `OPEN`→`IN_PROGRESS`, `IN_PROGRESS`→`RESOLVED`, `RESOLVED`→`CLOSED`) and **NEG**: every other (from,to) pair is rejected, including from `CLOSED` and `REJECTED`.
- [ ] T009 Implement status machine and creation routing (`ACCESS`→`PENDING_APPROVAL`, others→`OPEN`) (packages/domain/src/transitions.ts) — AC: T008 passes; creation routing is driven by category `requiresApproval`.
- [ ] T010 [P] Write unit tests for the authorization policy matrix from plan.md (tests/unit/domain/policy.test.ts) — AC: matrix rows for request:create/read/history/transition/assign, category:*, user:role-write, audit:read each have allow cases and **NEG** deny cases per role; unknown action is denied.
- [ ] T011 Implement the pure policy (`can(action, principal, resource)`) with default-deny (packages/domain/src/policy.ts) — AC: T010 passes; owner≠approver rule (self-approval forbidden) and assignee-only agent rule are implemented here; any action not listed returns deny.

### Persistence

- [ ] T012 Set up migration tooling and role split: owner role for migrations, least-privilege app role (packages/persistence/migrations/001_roles_enums.sql, packages/persistence/src/pool.ts) — AC: migration creates enums per T007 and an app role that cannot run DDL; `npm run db:migrate` is idempotent.
- [ ] T013 [P] Migration for `users` and `categories` (packages/persistence/migrations/002_users_categories.sql) — AC: columns exactly as data-model.md (`users.role` enum, `active` default true, `external_subject` unique nullable; `categories.code` PK, `requires_approval`, `active` default true).
- [ ] T014 Migration for `requests` and `request_status_history` (packages/persistence/migrations/003_requests_history.sql) — AC: `title` 1..120 chars, `description` 1..4000 chars, `CHECK (decided_by IS NULL OR decided_by <> owner_id)`, indexes on `owner_id`, `assignee_id`, `status`; history has `from_status` nullable.
- [ ] T015 Migration for `audit_log`, an UPDATE/DELETE-rejecting trigger, and app-role grants of INSERT and SELECT only (packages/persistence/migrations/004_audit_log.sql) — AC: columns per data-model.md (actor_id, action, target_type, target_id, http_request_id, occurred_at UTC, metadata jsonb).
- [ ] T016 **NEG** Test audit immutability as the app DB role (tests/api/audit-immutability.test.ts) — AC: UPDATE and DELETE on `audit_log` fail; INSERT and SELECT succeed (quickstart #13).
- [ ] T017 [P] Deterministic seed (dev/test only, never in production migrations): 2 employees, 2 agents, 2 managers, 1 admin, categories `IT`, `FACILITIES`, `ACCESS` (`requires_approval` true only for `ACCESS`), fake names only (packages/persistence/src/seed.ts, tests/fixtures/seed.ts) — AC: fixed UUIDs; no real data or PII (FR-033); seed refuses to run when `NODE_ENV=production`.
- [ ] T018 Implement transaction helper and audit writer (`writeAudit`) used inside the same transaction as changes (packages/persistence/src/tx.ts, packages/persistence/src/repositories/audit.ts) — AC: failed business write rolls back its audit row; audit write failure rolls back the business write (interim, flagged CHK028).
- [ ] T019 [P] Implement user and category repositories with parameterized queries only (packages/persistence/src/repositories/{users,categories}.ts) — AC: no string-concatenated SQL anywhere (grep-based lint rule in T003 config).

### API foundation

- [ ] T020 [P] Config loader with production guard: startup throws if `AUTH_MODE=dev` and `NODE_ENV=production`, and if `AUTH_MODE=oidc` ("not implemented in release 1") (apps/api/src/config/env.ts) — AC: unit tests cover all three outcomes.
- [ ] T021 **NEG** Test the production guard (tests/api/config-guard.test.ts) — AC: process/config creation fails for dev+production; dev routes are not mounted when `AUTH_MODE` is not `dev` (quickstart #14, FR-032).
- [ ] T022 Define `IdentityProvider` interface and dev adapter issuing a signed HttpOnly cookie (SameSite=Lax; Secure outside local dev) resolving `Principal {userId, role}` from the `users` table, never from the client (apps/api/src/auth/{identity-provider,dev-adapter,session}.ts) — AC: role comes only from the database row; inactive users cannot sign in; no token in response bodies.
- [ ] T023 [P] Add documented OIDC boundary stub: interface file with comments naming required validations (issuer, audience, expiry, nonce) and no implementation (apps/api/src/auth/oidc-boundary.ts) — AC: selecting it fails startup with a clear message; no password-handling code exists.
- [ ] T024 Implement request-ID middleware, error mapper (shape `{code,message,requestId}`), and not-found/forbidden mapping rule (apps/api/src/http/{request-id,errors}.ts) — AC: every error body matches the contract `Error` schema; unknown ID and not-visible ID produce byte-identical bodies except `requestId`.
- [ ] T025 Implement the authorization registry: routes register an `x-authz` action; middleware denies anything unregistered; API refuses to start with an unregistered route (apps/api/src/authz/registry.ts, apps/api/src/http/app.ts) — AC: authorization calls the domain policy only; deny-by-default.
- [ ] T026 Wire `express-openapi-validator` against `specs/001-servicedesk-lite/contracts/openapi.yaml` (requests always, responses in test/dev), plus CSRF defense (required custom header on state-changing methods) (apps/api/src/http/{app,openapi,csrf}.ts) — AC: invalid body → 400 with the standard error shape; state-changing call without the header → 403.
- [ ] T027 **NEG** Route-enumeration test: every Express route has an authorization action or is on the explicit public allow-list (`/health`, `/dev/session` in dev only) (tests/api/route-enumeration.test.ts) — AC: adding an unregistered route makes the test fail (quickstart #15, R-02).
- [ ] T028 **NEG** Unauthenticated test over all protected routes (tests/api/unauthenticated.test.ts) — AC: each protected operation in the contract returns 401 with no data (quickstart #8, FR-008).
- [ ] T029 [P] Contract test harness comparing live responses with the OpenAPI schemas (tests/contract/openapi.contract.test.ts) — AC: fails when a response violates its schema; runs under `npm run test:contract`.
- [ ] T030 Implement `GET /health`, `POST /dev/session`, `DELETE /session`, `GET /me` (apps/api/src/http/routes/{health,session}.ts) — AC: match contract; `/dev/session` returns 404 when dev mode is off.

**Checkpoint**: foundation ready; user stories can start.

---

## Phase 3: User Story 1 - Employee submits a service request (P1) 🎯 MVP

**Goal**: an employee creates a request, routed by category. **Independent Test**: sign in as an employee, submit, observe status and presence in own list (spec US1, quickstart #1, #2).

### Tests (write first)

- [ ] T031 [P] [US1] Integration tests for `POST /requests` (tests/api/requests-create.test.ts) — AC: `IT` → 201 `OPEN`; `ACCESS` → 201 `PENDING_APPROVAL`; owner = caller; history rows created (`SUBMITTED`, then routed status).
- [ ] T032 [P] [US1] **NEG** Validation tests (tests/api/requests-create-negative.test.ts) — AC: 400 for missing field, `title` empty or over 120, `description` empty or over 4000, unknown field, invalid priority, unknown or inactive category, SQL-injection and markup strings stored/returned as inert text; 401 when unauthenticated; no row is saved on any failure (FR-003).
- [ ] T033 [P] [US1] **NEG** Test that the client cannot set `ownerId`, `status`, `assigneeId` or role in the create body (tests/api/requests-create-mass-assignment.test.ts) — AC: unknown fields rejected with 400 (additionalProperties false).

### Implementation

- [ ] T034 [P] [US1] Request and history repositories with principal-scoped queries (packages/persistence/src/repositories/{requests,history}.ts) — AC: create inserts request, history rows and audit rows (`REQUEST_SUBMITTED`, `REQUEST_ROUTED`) in one transaction; quoted constraints: title 1..120, description 1..4000.
- [ ] T035 [US1] Zod schemas and `createRequest` service/controller (apps/api/src/http/schemas.ts, apps/api/src/http/routes/requests.ts) — AC: T031–T033 pass; controller validates then delegates; authorization action `request:create`.
- [ ] T036 [US1] `GET /categories` (active only for the create form; all for admin) (apps/api/src/http/routes/categories.ts) — AC: matches contract; employees never see inactive categories as choices (spec US1 #3).
- [ ] T037 [P] [US1] Web scaffold: Vite + React + Router, typed API client with the CSRF header, dev login picker shown only in dev (apps/web/src/{main.tsx,api/client.ts,auth/Login.tsx}, apps/web/vite.config.ts) — AC: signing in as each seeded user works locally; the picker is not built in production mode.
- [ ] T038 [US1] New-request page, mobile-first, with field-level validation messages (apps/web/src/pages/NewRequest.tsx, apps/web/src/styles.css) — AC: works at 360px and 1280px widths; user-supplied text is rendered as text, never as HTML (FR-028, Constitution III).

**Checkpoint**: US1 independently demonstrable.

---

## Phase 4: User Story 2 - Employee tracks only their own requests (P1)

**Goal**: own list, detail, timeline; cross-user access refused. **Independent Test**: two employees see only their own; direct access to the other's ID is refused (quickstart #6).

### Tests (write first)

- [ ] T039 [P] [US2] Integration tests for `GET /requests`, `GET /requests/{id}`, `GET /requests/{id}/history` as owner (tests/api/requests-read.test.ts) — AC: list contains only owner's requests; history ordered by time and complete.
- [ ] T040 [P] [US2] **NEG** Cross-user (IDOR/BOLA) tests (tests/api/requests-idor.test.ts) — AC: employee B gets 404 on A's request detail and history; the body equals the unknown-ID body; list never includes A's requests; filtering by `status` does not widen scope; guessing sequential/neighbor UUIDs yields 404.
- [ ] T041 [P] [US2] **NEG** Role-scope tests (tests/api/requests-visibility.test.ts) — AC: agent sees only assigned (404 otherwise); manager sees no non-approval requests; admin sees all; unauthenticated 401.

### Implementation

- [ ] T042 [US2] Implement scoped read repository methods (list/get/history take the principal; no unscoped `findById` exported) (packages/persistence/src/repositories/requests.ts) — AC: T039–T041 pass; scoping is in the SQL `WHERE`, not post-filtering.
- [ ] T043 [US2] Implement read endpoints with `request:read` and `request:history` actions (apps/api/src/http/routes/requests.ts) — AC: responses validate against the contract.
- [ ] T044 [P] [US2] My-requests list and request detail with status timeline (apps/web/src/pages/{RequestList,RequestDetail}.tsx) — AC: timeline shows status, actor and time; 404 renders a generic "not found" without distinguishing absent from forbidden.

**Checkpoint**: P1 stories complete = MVP.

---

## Phase 5: User Story 3 - Agent works assigned requests (P2)

**Goal**: admin assigns, agent starts and resolves, owner closes. **Independent Test**: quickstart #5, #7.

### Tests (write first)

- [ ] T045 [P] [US3] Integration tests for `PUT /requests/{id}/assignee` and transitions `OPEN→IN_PROGRESS→RESOLVED→CLOSED` (tests/api/requests-work.test.ts) — AC: full happy path reaches `CLOSED`; history and audit rows (`AGENT_ASSIGNED`, `STATUS_IN_PROGRESS`, `STATUS_RESOLVED`, `STATUS_CLOSED`) exist.
- [ ] T046 [P] [US3] **NEG** Assignment tests (tests/api/assign-negative.test.ts) — AC: non-admin (employee, agent, manager) → 403 and no change; assignee who is not an active AGENT → 400/409; assigning a request not in `OPEN` → 409; non-visible ID → 404.
- [ ] T047 [P] [US3] **NEG** Agent transition tests (tests/api/transition-agent-negative.test.ts) — AC: unassigned agent → 404; another agent's request → 404; assigned agent attempting `CLOSED`, `OPEN`, `REJECTED` or skipping to `RESOLVED` from `OPEN` → 409/403 per contract with status unchanged; employee/manager attempting start/resolve → 403.
- [ ] T048 [P] [US3] **NEG** Close tests (tests/api/close-negative.test.ts) — AC: non-owner employee → 404; owner closing a non-`RESOLVED` request → 409; agent/admin closing → 403; status unchanged in all cases.

### Implementation

- [ ] T049 [US3] Assignment and transition services using domain policy and status machine, history + audit in one transaction (apps/api/src/http/routes/transitions.ts, packages/persistence/src/repositories/requests.ts) — AC: T045–T048 pass; invalid transitions return the contract 409 shape.
- [ ] T050 [P] [US3] Agent queue page and actions (start/resolve) (apps/web/src/pages/AgentQueue.tsx) — AC: lists only assigned requests; buttons hidden when not permitted but the server remains the authority.
- [ ] T051 [P] [US3] Admin assignment control and owner "Close" action on resolved requests (apps/web/src/pages/RequestDetail.tsx) — AC: control visible only for the permitted role/state; server refusals are shown as clear messages.

---

## Phase 6: User Story 4 - Manager approval for ACCESS requests (P2)

**Goal**: ACCESS requests wait for a manager; self-approval forbidden. **Independent Test**: quickstart #3, #4.

### Tests (write first)

- [ ] T052 [P] [US4] Integration tests for approve/reject via `POST /requests/{id}/transitions` (tests/api/approval.test.ts) — AC: manager (non-owner) approve → `OPEN` with `decided_by` set, audit `APPROVAL_APPROVED`; reject → `REJECTED`, `APPROVAL_REJECTED`; employee sees outcome (FR-020); `IT` requests never enter approval.
- [ ] T053 [P] [US4] **NEG** Self-approval and role tests (tests/api/approval-negative.test.ts) — AC: a manager approving/rejecting their own `ACCESS` request is refused (and the DB `CHECK` also refuses `decided_by = owner_id` when attempted directly); employee/agent/admin attempting approve/reject → 403; approving a request not `PENDING_APPROVAL` → 409; second approval of an approved request → 409.
- [ ] T054 [P] [US4] **NEG** Work-before-approval test (tests/api/approval-gate.test.ts) — AC: assign and start/resolve on a `PENDING_APPROVAL` request are refused with status unchanged (FR-016).

### Implementation

- [ ] T055 [US4] Implement approval decisions and approver visibility rule (interim D-04: any `MANAGER` who is not the owner; flag in code comment referencing OQ-06) (apps/api/src/http/routes/transitions.ts, packages/persistence/src/repositories/requests.ts) — AC: T052–T054 pass; the interim rule is isolated in one function for easy replacement.
- [ ] T056 [P] [US4] Manager approvals page with approve/reject (apps/web/src/pages/Approvals.tsx) — AC: lists only requests the API returns; no client-side role trust.

---

## Phase 7: User Story 6 - Auditable change history (P2)

**Goal**: audit entries are complete, restricted and immutable. **Independent Test**: quickstart #13 plus audit listing.

### Tests (write first)

- [ ] T057 [P] [US6] Integration tests for audit coverage (tests/api/audit-events.test.ts) — AC: every state transition, assignment, category change and role change writes an entry with actor ID, action, target, request ID, UTC timestamp; entries contain no secrets or personal data beyond IDs.
- [ ] T058 [P] [US6] **NEG** Audit access tests (tests/api/audit-access-negative.test.ts) — AC: employee, agent, manager → 403 on `GET /audit`; unauthenticated → 401; no route exists that updates or deletes audit entries (verified by route enumeration); a failed/rolled-back change leaves no audit row.

### Implementation

- [ ] T059 [US6] Implement `GET /audit` (interim: ADMIN only, flagged OQ-11) with optional `requestId` filter (apps/api/src/http/routes/audit.ts) — AC: T057–T058 pass; response matches contract.
- [ ] T060 [P] [US6] Ensure all mutating services call `writeAudit` for the events in plan.md §Audit Events (apps/api/src/http/routes/*.ts) — AC: audit coverage test (T057) is the proof; denials (`AUTH_DENIED`) are logged only if the reviewer decided in T001, otherwise omitted.

---

## Phase 8: User Story 5 - Administrator manages categories and roles (P3)

**Goal**: manage categories without losing history; manage roles. **Independent Test**: spec US5 and quickstart #9, #12.

### Tests (write first)

- [ ] T061 [P] [US5] Integration tests for category create/update/deactivate and role change (tests/api/admin.test.ts) — AC: deactivated category stays on existing requests and is rejected for new ones; role change takes effect on the next request and writes `ROLE_CHANGED`/`CATEGORY_*` audit entries.
- [ ] T062 [P] [US5] **NEG** Admin-only tests (tests/api/admin-negative.test.ts) — AC: employee, agent, manager → 403 on category create/update, `GET /users`, `PUT /users/{id}/role`; invalid role value or unknown user → 400/404; invalid category code pattern `^[A-Z_]{2,32}$` → 400; unauthenticated 401.

### Implementation

- [ ] T063 [US5] Implement `POST /categories`, `PATCH /categories/{code}`, `GET /users`, `PUT /users/{id}/role` (apps/api/src/http/routes/{categories,users}.ts) — AC: T061–T062 pass; categories are never deleted; new categories default to `requires_approval = false` unless the reviewer decided otherwise in T001 (CHK023).
- [ ] T064 [P] [US5] Admin pages for categories, roles and all-requests view (apps/web/src/pages/Admin.tsx) — AC: admin sees all requests (DR-06); non-admin navigation to the page shows a generic refusal while the server enforces access.

---

## Phase 9: Polish & Cross-Cutting

- [ ] T065 [P] Run the full quickstart scenario table and record results (specs/001-servicedesk-lite/quickstart.md, tests/api) — AC: each of the 15 scenarios maps to a named automated test or a recorded manual check; unmapped ones are listed as gaps.
- [ ] T066 [P] Manual access checks on desktop and a phone-width viewport for each role; record evidence (specs/001-servicedesk-lite/evidence/manual-access.md) — AC: results recorded, not asserted.
- [ ] T067 [P] Log redaction and no-secrets scan: logs contain no tokens, cookies or request bodies; repo scan finds no secrets (apps/api/src/http/logging.ts, tests/api/logging.test.ts) — AC: **NEG** test asserts that cookie and authorization values never appear in captured logs.
- [ ] T068 [P] Dependency review: lockfile committed, `npm audit` output reviewed and any accepted finding recorded with owner and expiry (specs/001-servicedesk-lite/evidence/dependency-review.md) — AC: no silent suppression (Constitution VIII).
- [ ] T069 Run Gate F: `npm run ci` plus contract tests (repo root) — AC: all commands exit 0, and their output is saved as evidence; any failure stops release (A failed gate means stop, inspect, revise).
- [ ] T070 Run `/speckit-analyze` for cross-artifact consistency (Gate E) and resolve critical findings before declaring release 1 ready (specs/001-servicedesk-lite) — AC: no unaddressed critical inconsistency.

---

## Dependencies & Execution Order

- **Phase 1** → **Phase 2** (blocks everything) → stories.
- **US1 (P1)** and **US2 (P1)**: US2 reads what US1 creates; US2 tests can be written in parallel with US1 but T042 depends on T034.
- **US3** depends on US1 (requests exist) and T018 (audit writer).
- **US4** depends on US1; independent of US3 except the shared transitions route file (T049 before T055 to avoid file conflicts).
- **US6** depends on Phase 2 audit pieces; T060 touches routes from US1–US5, so it finishes after them.
- **US5** depends on Phase 2 only (categories/users repositories); its audit events depend on T018.
- **Polish** last.

Within each story: tests → repositories → services/routes → web pages.

## Parallel Examples

- Phase 2: T007, T008, T010, T013, T017, T019, T020, T023 can run together (distinct files).
- US1: T031, T032, T033 (tests) together; then T034 and T037 together.
- US3/US4/US5 test tasks (T045–T048, T052–T054, T061–T062) can be written in parallel by different people.

## Implementation Strategy

1. **MVP**: Phases 1–2, then US1 and US2 (P1). Stop and demo: create and track own requests, with cross-user refusal.
2. Add US3 → US4 → US6 → US5 incrementally; each phase ends with its negative tests passing.
3. Do not implement items listed under "Open items"; if a task needs one, stop and run `/speckit-clarify`.

## Traceability (FR → tasks)

FR-001..006 → T031–T044; FR-008..011 → T011, T025, T027, T028, T040, T041; FR-012..015, 030 → T045–T051; FR-016..020 → T052–T056; FR-021..023 → T061–T064; FR-024..026 → T015, T016, T018, T057–T060; FR-027 → T008, T009, T049; FR-028 → T038, T066; FR-031 → T041, T042; FR-032 → T020–T023; FR-033 → T017. FR-007 (edit/cancel) is intentionally unimplemented (OQ-03).
