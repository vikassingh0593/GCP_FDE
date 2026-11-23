# Data Model: ServiceDesk Lite

All timestamps are UTC (`timestamptz`). IDs are UUIDs. Interim choices are flagged with the
plan's decision IDs.

## users
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| display_name | text, not null | fake names only (DR-10) |
| role | enum `EMPLOYEE|AGENT|MANAGER|ADMIN` | single role (OQ-04) |
| active | boolean, default true | |
| external_subject | text, unique, null | future OIDC `sub` mapping (D-01) |

## categories
| Column | Type | Notes |
|--------|------|-------|
| code | text PK | seed: `IT`, `FACILITIES`, `ACCESS` (DR-02) |
| name | text, not null | |
| requires_approval | boolean | true only for `ACCESS` |
| active | boolean, default true | deactivation keeps history (FR-022) |

## requests
| Column | Type | Notes |
|--------|------|-------|
| id | uuid PK | |
| title | text, 1..120 chars | validated |
| description | text, 1..4000 chars | |
| category_code | text FK → categories | |
| priority | enum `LOW|MEDIUM|HIGH` | placeholder values (D-08) |
| status | enum of DR-03 | |
| owner_id | uuid FK → users, not null | ownership anchor |
| assignee_id | uuid FK → users, null | set by ADMIN, must be AGENT |
| decided_by | uuid FK → users, null | approver; ≠ owner (CHECK) |
| created_at, updated_at | timestamptz | |

Constraints: `CHECK (decided_by IS NULL OR decided_by <> owner_id)`; `assignee_id` must reference
an active AGENT (enforced in service, verified by test). Indexes: `(owner_id)`,
`(assignee_id)`, `(status)`.

## request_status_history (timeline shown to authorized readers)
| Column | Type | Notes |
|--------|------|-------|
| id | bigserial PK | |
| request_id | uuid FK | |
| from_status | enum, null | null for creation |
| to_status | enum | |
| actor_id | uuid FK | |
| occurred_at | timestamptz | |

## audit_log (append-only at application/DB-grant level; not tamper-proof)
| Column | Type | Notes |
|--------|------|-------|
| id | bigserial PK | |
| actor_id | uuid | |
| action | text | event names in plan |
| target_type | text | `REQUEST|CATEGORY|USER` |
| target_id | text | request ID for request events |
| http_request_id | text | correlation ID |
| occurred_at | timestamptz | |
| metadata | jsonb | no PII or secrets |

Grants: app role INSERT, SELECT only; trigger rejects UPDATE/DELETE.

## Transition table (domain constant, mirrored by test)
| From | To | Actor | Extra rule |
|------|----|-------|-----------|
| (create, ACCESS) | PENDING_APPROVAL | owner | |
| (create, other) | OPEN | owner | |
| PENDING_APPROVAL | OPEN | MANAGER | caller ≠ owner |
| PENDING_APPROVAL | REJECTED | MANAGER | caller ≠ owner |
| OPEN | IN_PROGRESS | assigned AGENT | requires assignee |
| IN_PROGRESS | RESOLVED | assigned AGENT | |
| RESOLVED | CLOSED | owner | |

Terminal: `CLOSED`, `REJECTED`. Assignment (ADMIN) is allowed while `OPEN` and does not
change status.

## Seed (deterministic fixtures, fake data only)
Users: 2 employees, 1 agent (plus a second agent for cross-agent tests), 2 managers, 1 admin.
Categories: the three above. A fixed set of requests across statuses for tests.

## Migration order
1. roles, enums, users, categories 2. requests, history 3. audit_log + trigger + grants
4. seed (dev/test only, never in production migrations).
