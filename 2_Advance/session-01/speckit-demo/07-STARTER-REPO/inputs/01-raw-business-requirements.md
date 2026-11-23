# RAW BUSINESS REQUEST — ServiceDesk Lite
**Source:** Fictional stakeholder intake. **Status:** Not approved for implementation. **Do not treat unspecified behavior as settled.**

Our organization wants a simple internal service-request portal. Employees should be able to raise requests for facilities, IT equipment, and access-related assistance. A request should have a short title, description, category and priority. Employees should see the status of their own requests.

A service agent should see assigned requests and update progress. Some requests need manager approval before the service team starts work. We want an audit trail of changes. Admins should manage categories and roles.

The system should be easy to use on desktop and mobile. It should be secure, support multiple teams, and allow reporting later. The first release should be small and demonstrable.

## Known user groups
- Employee: raises and tracks own requests
- Service Agent: works on assigned requests
- Manager: approves certain requests
- Administrator: manages categories and role assignment

## Unresolved questions (intentional)
- Which categories or amounts require approval?
- Who assigns a service agent?
- Can employees edit or cancel after submission?
- Can managers approve their own requests?
- What statuses and transitions are permitted?
- What does “multiple teams” mean: teams within one company or separate tenants?
- Which notifications are required?
- Is authentication corporate SSO or local accounts?
- Which reports are in release 1?
- What retention and privacy requirements apply?

**Trainer note:** A good specification labels these unknowns; it does not invent confirmed answers.
