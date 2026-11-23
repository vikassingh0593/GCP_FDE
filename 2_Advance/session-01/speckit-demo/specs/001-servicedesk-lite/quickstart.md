# Quickstart & Validation Guide: ServiceDesk Lite

Validation scenarios for the finished feature. Commands name the scripts the implementation
MUST provide (they do not exist yet). Details: [data-model.md](data-model.md),
[contracts/openapi.yaml](contracts/openapi.yaml), [plan.md](plan.md).

## Prerequisites
Node.js 20+, Docker, npm. Copy `.env.example` to `.env` (placeholders only; no real secrets).
Local demo uses `AUTH_MODE=dev` and fake seeded users.

## Setup and run
```bash
npm install
docker compose up -d db
npm run db:migrate && npm run db:seed     # seed is dev/test only
npm run dev                                # api + web
```

## Automated checks (Gate F)
```bash
npm run typecheck && npm run lint
npm test                    # unit + API integration + contract
npm run test:contract       # implementation vs openapi.yaml
npm audit                   # failures need a recorded review, not suppression
```

## Scenarios

| # | Scenario | Expected | Spec |
|---|----------|----------|------|
| 1 | Employee creates `IT` request | 201, status `OPEN`, in own list | FR-001, 018 |
| 2 | Employee creates `ACCESS` request | status `PENDING_APPROVAL` | FR-018 |
| 3 | Manager (not owner) approves | `OPEN`; history + audit rows | FR-017 |
| 4 | Owner who is a manager approves own request | refused | FR-019 |
| 5 | Admin assigns agent; agent starts, resolves; owner closes | `CLOSED`, history rows | FR-013, 015, 030 |
| 6 | Employee B requests employee A's request by ID | 404, same body as unknown ID | FR-009 |
| 7 | Agent opens an unassigned request | 404 | FR-012 |
| 8 | Unauthenticated call to any route except health/dev session | 401 | FR-008 |
| 9 | Non-admin calls category write, role write, assign, audit | 403 | FR-021, 023 |
| 10 | Invalid transition (e.g. `OPEN`→`CLOSED`) | 409, status unchanged | FR-027 |
| 11 | Malformed body, oversize title, unknown fields | 400 | FR-003 |
| 12 | Deactivate a used category | old requests unchanged; new create rejected | FR-022 |
| 13 | UPDATE/DELETE on `audit_log` as the app DB role | rejected by DB | FR-025 |
| 14 | Start API with `AUTH_MODE=dev` and `NODE_ENV=production` | process exits with error | FR-032 |
| 15 | Route enumeration | every route has an `x-authz` action or is denied | FR-008 |

Scenarios 4, 6–11, 13–15 are the negative security tests required by Constitution VI.

## Manual access checks
In the browser, sign in as each seeded role through the dev picker and confirm the screens and
the 404/403 behavior above on desktop and a phone-width viewport. Manual checks are evidence
only when their results are recorded.
