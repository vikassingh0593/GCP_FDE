# FICTIONAL WORKSHOP DECISION RECORD — APPROVED FOR EXERCISE ONLY
**Purpose:** Resolve blocking ambiguities so the class can reach implementation. These are synthetic classroom decisions, not organizational policy.

- DR-01: Release 1 is **single-organization**, with internal teams; multi-tenancy is out of scope.
- DR-02: Categories `IT`, `FACILITIES`, `ACCESS`. Only `ACCESS` requires manager approval.
- DR-03: Request statuses: `SUBMITTED`, `PENDING_APPROVAL`, `OPEN`, `IN_PROGRESS`, `RESOLVED`, `CLOSED`, `REJECTED`.
- DR-04: `ACCESS` requests enter `PENDING_APPROVAL`. Manager may approve/reject; self-approval forbidden. Approved requests move to `OPEN`.
- DR-05: Other requests enter `OPEN`. An Admin assigns agents; assigned agents may set `IN_PROGRESS` and `RESOLVED`; employee may close own `RESOLVED` request.
- DR-06: Employees may view only their own requests. Agents view only assigned requests. Managers see approval requests addressed to them. Admins can view all requests.
- DR-07: First release uses **mocked development identity** behind an explicit interface; production integration must use corporate OIDC. Demo identity must never be accepted as production auth.
- DR-08: Notifications, attachments, reports, SLAs and multi-tenancy are out of scope for release 1.
- DR-09: Record actor ID, action, request ID and UTC timestamp for every state transition; audit log append-only at application level.
- DR-10: No customer PII or real organization data in the demo.

**Teaching mechanism:** Run `/speckit.specify` from raw brief first, use `/speckit.clarify` to identify gaps, then supply this decision record as stakeholder responses and revise spec.
