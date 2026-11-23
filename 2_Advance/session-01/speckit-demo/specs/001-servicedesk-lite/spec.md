# Feature Specification: ServiceDesk Lite

**Feature Branch**: `001-servicedesk-lite` (spec directory only; no git branch created)

**Created**: 2026-11-17

**Status**: Draft

**Input**: User description: "Use 07-STARTER-REPO/inputs/01-raw-business-requirements.md and 07-STARTER-REPO/inputs/02-stakeholder-personas-and-notes.md to specify ServiceDesk Lite. Include prioritized user stories, requirement IDs, acceptance scenarios, scope boundaries and unanswered questions. Do not invent stakeholder policy decisions or select implementation technologies here."

> **Policy discipline**: The source material is explicitly "not approved for implementation".
> Where stakeholders have not decided a behavior, this spec records an **Open Question (OQ-nn)**
> and writes the related requirement in a policy-neutral form. No unresolved policy is treated as
> settled. Any "Assumption" below is a planning convenience, never a stakeholder decision.

## Clarifications

### Session 2026-11-17

Source: `07-STARTER-REPO/inputs/03-workshop-policy-decisions.md` (DR-01..DR-10), a fictional
classroom decision record approved for the exercise only, not organizational policy. Only
questions it answers were resolved; the rest remain in Open Questions.

- Q: Single organization or separate tenants? → A: Single organization with internal teams;
  multi-tenancy out of scope (DR-01). Resolves OQ-07 in part.
- Q: Categories and which need approval? → A: `IT`, `FACILITIES`, `ACCESS`; only `ACCESS`
  requires manager approval (DR-02). Resolves OQ-01, OQ-06 in part.
- Q: Which statuses exist? → A: `SUBMITTED`, `PENDING_APPROVAL`, `OPEN`, `IN_PROGRESS`,
  `RESOLVED`, `CLOSED`, `REJECTED` (DR-03). Resolves OQ-05 in part.
- Q: How does approval work, and may managers self-approve? → A: `ACCESS` requests enter
  `PENDING_APPROVAL`; a manager approves (→ `OPEN`) or rejects; self-approval forbidden (DR-04).
  Resolves OQ-04 in part.
- Q: Who assigns agents and who moves requests forward? → A: Other categories enter `OPEN`; an
  Administrator assigns agents; assigned agents set `IN_PROGRESS` and `RESOLVED`; the employee
  may close their own `RESOLVED` request (DR-05). Resolves OQ-02.
- Q: Who can see which requests? → A: Employees own only; agents assigned only; managers the
  approval requests addressed to them; administrators all (DR-06).
- Q: Identity source? → A: Mocked development identity behind an explicit interface for release 1;
  production integration must use corporate OIDC; the mock must never be accepted as production
  authentication (DR-07). Resolves OQ-12.
- Q: Notifications, attachments, reports, SLAs, multi-tenancy? → A: All out of scope for release 1
  (DR-08). Resolves OQ-08, OQ-09.
- Q: What must the audit record? → A: Actor ID, action, request ID and UTC timestamp for every
  state transition; application-level append-only (DR-09).
- Q: Real data in the demo? → A: No customer PII or real organization data (DR-10).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Employee submits a service request (Priority: P1)

An employee raises a request for facilities, IT equipment, or access-related assistance by
providing a short title, a description, a category, and a priority.

**Why this priority**: Without request creation nothing else in the portal has value. This is the
smallest demonstrable slice and matches the stakeholder signal "create a request with a title,
category and description".

**Independent Test**: Sign in as an employee, submit a request with all fields, and confirm it
exists with an initial status and appears in that employee's list.

**Acceptance Scenarios**:

1. **Given** a signed-in employee, **When** they submit a request with title, description,
   category and priority, **Then** the request is saved, is owned by that employee, and starts
   in `PENDING_APPROVAL` if the category is `ACCESS`, otherwise in `OPEN`.
2. **Given** a signed-in employee, **When** they submit a request with a missing or invalid
   required field, **Then** the request is rejected with a clear message identifying the field,
   and nothing is saved.
3. **Given** a signed-in employee, **When** they choose a category that has been deactivated,
   **Then** it is not offered for new requests.

---

### User Story 2 - Employee tracks only their own requests (Priority: P1)

An employee sees a list of their own requests and, for each, its current status and a timeline of
status changes, without calling IT. Employees can never see another employee's requests.

**Why this priority**: It is the second half of the employee value ("follow my requests") and
carries the security reviewer's non-negotiable requirement.

**Independent Test**: With two employees each owning requests, confirm each sees only their own,
and that direct access to the other's request is refused.

**Acceptance Scenarios**:

1. **Given** an employee with several requests, **When** they open their list, **Then** only
   their own requests are shown with current status.
2. **Given** an employee viewing one of their requests, **When** they open it, **Then** a
   timeline of status changes is shown.
3. **Given** employee A and a request owned by employee B, **When** A attempts to open B's
   request by any means (including guessing its identifier), **Then** access is refused and no
   information about B's request is revealed.
4. **Given** an unauthenticated visitor, **When** they attempt to view any request, **Then**
   access is refused.

---

### User Story 3 - Service agent works assigned requests (Priority: P2)

An administrator assigns requests to service agents. A service agent sees a queue of requests
assigned to them, sets them `IN_PROGRESS` and `RESOLVED`, and can see the history of changes on
each. The employee who raised a `RESOLVED` request may close it.

**Why this priority**: Requests have no outcome until an agent can act on them, but the portal is
demonstrable for employees first.

**Independent Test**: Assign a request to an agent, confirm it appears only in that agent's
queue, update its status, and confirm the change appears in the history.

**Acceptance Scenarios**:

1. **Given** an agent with assigned requests, **When** they open their queue, **Then** only
   requests assigned to them are listed.
2. **Given** an assigned `OPEN` request, **When** the agent sets it `IN_PROGRESS` and later
   `RESOLVED`, **Then** each status change is applied and recorded in the history (who, what,
   when).
3. **Given** an `OPEN` request, **When** an administrator assigns an agent, **Then** the request
   appears in that agent's queue; **When** a non-administrator tries to assign, **Then** it is
   refused.
4. **Given** a `RESOLVED` request, **When** its owning employee closes it, **Then** it becomes
   `CLOSED`; **When** any other employee tries, **Then** it is refused.
5. **Given** a request not assigned to the agent, **When** the agent tries to view or update it,
   **Then** access is refused.
6. **Given** an assigned request, **When** the agent attempts a status change that is not
   permitted, **Then** it is rejected and the status is unchanged. (Undecided transitions: OQ-05.)

---

### User Story 4 - Manager approves requests that need approval (Priority: P2)

For requests that require approval, a manager approves or rejects before the service team starts
work. Approval must not delay routine work.

**Why this priority**: Stakeholders want "one approval flow" demonstrated, but which requests need
approval is undecided, so this follows the core submit/track/work flow.

**Independent Test**: Mark a request as needing approval, confirm work cannot start, then approve
it as a manager and confirm work can begin; repeat with a rejection.

**Acceptance Scenarios**:

1. **Given** a request that requires approval, **When** it has not been approved, **Then** the
   service team cannot start work on it.
2. **Given** a request awaiting approval, **When** an authorized manager approves it, **Then** it
   becomes eligible for work and the decision (who, when) is recorded.
3. **Given** a request awaiting approval, **When** an authorized manager rejects it, **Then**
   work does not start and the employee can see the outcome.
4. **Given** a request in `IT` or `FACILITIES`, **When** it is submitted, **Then** it goes
   directly to `OPEN` without an approval step.
5. **Given** an approved request, **Then** it is `OPEN`; a rejected request becomes `REJECTED`.
6. **Given** a user who is not an authorized approver for a request, **When** they attempt to
   approve it, **Then** the attempt is refused.
7. **Given** a manager who raised a request, **When** the approval decision is attempted by that
   same manager, **Then** it is refused (self-approval forbidden, DR-04).

---

### User Story 5 - Administrator manages categories and roles (Priority: P3)

An administrator creates and edits categories, deactivates categories without losing historical
requests, and assigns roles to users.

**Why this priority**: Needed to operate the portal, but a small fixed set of categories and
roles can support an initial demo.

**Independent Test**: Deactivate a category in use and confirm existing requests keep it, while
new requests cannot select it.

**Acceptance Scenarios**:

1. **Given** an administrator, **When** they deactivate a category that has existing requests,
   **Then** those requests remain intact and still display the category, and new requests cannot
   use it.
2. **Given** an administrator, **When** they assign or change a user's role, **Then** the change
   takes effect and is recorded in the audit trail.
3. **Given** a non-administrator, **When** they attempt to manage categories or roles, **Then**
   the attempt is refused.
4. **Given** an administrator, **When** they list requests, **Then** all requests are visible
   (DR-06).

---

### User Story 6 - Auditable change history (Priority: P2)

Every change to a request, approval decision, category, and role assignment is recorded with who,
what, when, and target, and the record cannot be altered by ordinary users.

**Why this priority**: Explicitly requested ("audit trail of changes") and relied on by both the
agent and employee timelines.

**Independent Test**: Perform a status change and a role change, then confirm each appears in the
audit trail with actor, action, time and target, and that ordinary users cannot edit or delete
entries.

**Acceptance Scenarios**:

1. **Given** any recorded change, **When** the audit trail is viewed by an authorized user,
   **Then** actor, action, time and target are shown.
2. **Given** any user without audit permission, **When** they try to view or modify audit
   entries, **Then** the attempt is refused. (Who may view audit data: OQ-11.)

---

### Edge Cases

- A user holds more than one role (for example, manager and employee): which view and
  permissions apply? (OQ-04)
- A category is deactivated while a request is mid-submission.
- An `OPEN` request has no assigned agent yet: it stays unworked until an administrator assigns one.
- A user is deactivated or has a role removed while owning or being assigned requests.
- Two actors update the same request at nearly the same time.
- Extremely long or malformed titles and descriptions; markup or script content in text fields.
- An employee tries to edit or cancel a request after submission. (OQ-03)
- Repeated or rapid submissions of the same request.
- A request references an identifier that does not exist versus one the user is not allowed to
  see (the user must not be able to tell the difference).

## Requirements *(mandatory)*

### Functional Requirements

**Requests**

- **FR-001**: Authenticated employees MUST be able to create a service request with a title,
  description, category, and priority.
- **FR-002**: The system MUST support the categories `IT`, `FACILITIES` and `ACCESS` (DR-02);
  administrators manage categories (FR-021).
- **FR-003**: The system MUST reject requests with missing or invalid required fields and report
  which field failed.
- **FR-004**: Each request MUST record its owner (the creating employee), creation time, and
  current status.
- **FR-005**: Employees MUST be able to view a list of their own requests and the current status
  of each.
- **FR-006**: Employees MUST be able to view, for each of their requests, a timeline of status
  changes.
- **FR-007**: Whether employees may edit or cancel a request after submission is undecided and
  MUST NOT be implemented until resolved. (OQ-03)

**Access control and privacy**

- **FR-008**: The system MUST deny any access that is not explicitly permitted, requiring
  authentication for all request data.
- **FR-009**: An employee MUST NOT be able to read or act on another employee's request, and a
  refusal MUST NOT reveal whether the request exists.
- **FR-010**: Access decisions MUST be made by the system's server side and MUST NOT depend on
  role information supplied by the user's device.
- **FR-011**: The portal MUST distinguish four roles: Employee, Service Agent, Manager, and
  Administrator.

**Agent work**

- **FR-012**: Service agents MUST be able to view a queue containing only requests assigned to
  them.
- **FR-013**: Assigned service agents MUST be able to set `IN_PROGRESS` and `RESOLVED` on
  requests assigned to them (DR-05), limited to permitted transitions (FR-027).
- **FR-014**: Service agents MUST be able to view the change history of requests assigned to
  them.
- **FR-015**: Only administrators MUST be able to assign a service agent to a request (DR-05);
  assignment MUST be recorded.
- **FR-030**: The employee who owns a `RESOLVED` request MUST be able to close it (`CLOSED`);
  no one else may (DR-05).
- **FR-031**: Visibility MUST be: employees their own requests; agents assigned requests;
  managers the approval requests addressed to them; administrators all requests (DR-06).

**Approval**

- **FR-016**: The system MUST support a state in which a request requires approval before work
  begins, and MUST prevent work from starting until approved.
- **FR-017**: Authorized managers MUST be able to approve or reject a request awaiting their
  approval, and the decision MUST be recorded with who and when.
- **FR-018**: Only `ACCESS` requests require approval and enter `PENDING_APPROVAL`; `IT` and
  `FACILITIES` requests enter `OPEN` with no approval step (DR-02, DR-04). Approved requests
  move to `OPEN`; rejected requests move to `REJECTED`.
- **FR-019**: Self-approval MUST be forbidden: a user MUST NOT approve or reject a request they
  raised (DR-04).
- **FR-020**: Employees MUST be able to see the outcome of an approval decision on their request.

**Administration**

- **FR-021**: Administrators MUST be able to create, edit, activate and deactivate categories.
- **FR-022**: Deactivating a category MUST NOT alter or remove existing requests that use it, and
  MUST prevent the category from being chosen for new requests.
- **FR-023**: Administrators MUST be able to assign and change user roles; non-administrators
  MUST NOT.

**Audit**

- **FR-024**: The system MUST record an audit entry (actor ID, action, request ID, UTC
  timestamp) for every request state transition (DR-09). The original brief also asks for an
  audit trail of changes generally; recording assignments, category changes, and role changes
  is retained from that brief and is not contradicted by DR-09.
- **FR-025**: Audit entries MUST be protected from modification or deletion by ordinary users,
  and viewing them MUST be restricted. (Who may view: OQ-11.)
- **FR-026**: The audit trail is append-only at application level (DR-09) and MUST NOT be
  described as tamper-proof.
- **FR-032**: Release 1 MUST obtain identity through a mocked development identity behind an
  explicit interface; production MUST use corporate OIDC, and the mock MUST NEVER be accepted
  as production authentication (DR-07).
- **FR-033**: The demo MUST contain no customer PII or real organization data (DR-10).

**Status model**

- **FR-027**: Request statuses are `SUBMITTED`, `PENDING_APPROVAL`, `OPEN`, `IN_PROGRESS`,
  `RESOLVED`, `CLOSED`, `REJECTED` (DR-03). Status changes MUST follow an explicit set of
  permitted transitions; invalid transitions MUST be rejected. Decided transitions:
  `PENDING_APPROVAL`→`OPEN` (approve), `PENDING_APPROVAL`→`REJECTED` (reject),
  `OPEN`→`IN_PROGRESS`, `IN_PROGRESS`→`RESOLVED` (agent), `RESOLVED`→`CLOSED` (owner). Any
  other transition (including the role of `SUBMITTED`, reopening, and cancellation) is
  undecided and MUST NOT be permitted until resolved (OQ-05).

**Experience**

- **FR-028**: All user-facing functions MUST be usable on both desktop and mobile screen sizes.
- **FR-029**: The first release MUST be limited to the scope in "Scope Boundaries" below.

### Key Entities

- **Service Request**: A user's request with title, description, category, priority, owner,
  status, optional assignee, approval state, and timestamps.
- **Category**: A classification for requests (for example facilities, IT equipment, access);
  has an active/inactive state and persists on historical requests.
- **User**: A person who signs in; has a role (Employee, Service Agent, Manager, Administrator).
- **Approval Decision**: Outcome (approved/rejected) for a request, with approver and time.
- **Status Change**: A recorded transition of a request between statuses, with actor and time.
- **Audit Entry**: A record of who did what, when, to which target.
- **Team**: An internal grouping of users within the single organization (DR-01). Its effect on
  access or assignment is not decided. (OQ-07)

## Scope Boundaries

**In scope for release 1** (small and demonstrable):

- Submit requests (P1), track own requests with status timeline (P1)
- Agent queue and progress updates (P2)
- One demonstrable approval flow with explicitly decided policy (P2)
- Audit trail of changes (P2)
- Category and role administration (P3)
- Desktop and mobile usability

**Out of scope / deferred** (not requested for release 1 or explicitly "later"):

- Notifications, attachments, reports, SLAs and multi-tenancy (DR-08, DR-01)
- Comments, escalation, integrations with external systems (not mentioned in the source
  material; not part of this specification)

## Open Questions

### Resolved by the workshop decision record

| ID | Resolution |
|--------|-----------|
| OQ-01 | Resolved: `IT`, `FACILITIES`, `ACCESS` (DR-02) |
| OQ-02 | Resolved: administrator assigns agents (DR-05) |
| OQ-08 | Resolved: notifications out of scope (DR-08) |
| OQ-09 | Resolved: reports out of scope (DR-08) |
| OQ-12 | Resolved: mock dev identity; production corporate OIDC (DR-07) |

### Still open (not answered by the record)

| ID | Question | Affects |
|--------|----------|---------|
| OQ-03 | Can employees edit or cancel a request after submission, and until when? DR-05 only lets the owner close a `RESOLVED` request. | FR-007 |
| OQ-04 | How are users who hold more than one role handled? (Self-approval itself is decided: forbidden.) | Edge cases |
| OQ-05 | Which other transitions are allowed: the role of `SUBMITTED`, reopening, cancellation, changes after `CLOSED` or `REJECTED`? | FR-027 |
| OQ-06 | How is the approving manager determined for a request ("addressed to them")? Approval need by amount is moot since only category counts (DR-02). | FR-016, FR-031 |
| OQ-07 | What do internal teams affect (visibility, assignment, nothing)? | Team entity |
| OQ-10 | What retention and deletion rules apply? (Only "no real data in demo" is decided, DR-10.) | FR-025 |
| OQ-11 | Who may view audit data (administrators, managers, agents)? | FR-025 |

## Success Criteria *(mandatory)*

The source says metrics are illustrative and **not approved**; these are demonstration outcomes,
not SLA commitments.

### Measurable Outcomes

- **SC-001**: An employee can create a request with a title, category and description and see it
  in their list in a single sitting, without help from IT.
- **SC-002**: For an authorized request, a status timeline is shown to the person entitled to see
  it.
- **SC-003**: In testing, 100% of attempts by one employee to read another employee's request are
  refused.
- **SC-004**: One approval flow is demonstrated end to end (approve and reject), with every
  policy decision it relies on explicitly recorded by stakeholders.
- **SC-005**: Every change listed in FR-024 appears in the audit trail with actor, action, time
  and target.
- **SC-006**: Deactivating a category leaves 100% of existing requests unchanged and viewable.
- **SC-007**: The primary flows (submit, track, update, approve) can be completed on both a
  phone-sized and a desktop-sized screen.

## Assumptions

- Users are internal employees of a single organization; whether separate organizations are
  involved is OQ-07.
- A user holds one role at a time until OQ-04 is decided.
- Decisions DR-01..DR-10 are fictional classroom decisions, not organizational policy.
- Technology, hosting, and authentication mechanisms are decided later in planning, under the
  project constitution, and are not specified here.
- Priority values and initial status names are placeholders pending OQ-05 and are not
  stakeholder decisions.
