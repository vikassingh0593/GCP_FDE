# SECURITY & PRIVACY CONSTITUTION INPUT
**Instructor-supplied non-negotiable controls.**

1. Default deny. Authorize each API action and object access on server; never trust frontend role labels.
2. Production auth uses OIDC Authorization Code + PKCE with a vetted provider; never build a password store. Training mode may use an explicit fake identity adapter **only for local demos**, disabled in production.
3. Enforce role + ownership checks; no IDOR/BOLA: users cannot fetch other users' requests by guessing IDs.
4. Input validation at API boundary, parameterized queries/ORM, output encoding, no raw SQL concatenation.
5. Secure session/token handling; no tokens in localStorage if avoidable; set secure cookie attributes if cookies are used; CSRF controls appropriate to session design.
6. No secrets in Git, source, prompts, logs or test fixtures; use environment variables and `.env.example` with placeholders.
7. Avoid PII in logs; minimize data, document retention and deletion policy as an **open production decision**.
8. Audit trail records actor/action/time/target, is protected against unauthorized modification, and is tested. App-level append-only is **not tamper-proof**.
9. Dependency hygiene: pinned lockfile, review known vulnerabilities, least-privilege database account.
10. Test positive and negative paths: unauthorized, forbidden, self-approval, cross-user access, invalid transition, malformed input.
11. No claim of compliance certification, penetration-test completion, or production hardening merely because generated docs say so.
12. Security exceptions require a documented risk decision; do not silently weaken controls to pass a demo.
