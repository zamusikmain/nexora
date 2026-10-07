# Architecture
## Decisions (before implementation)
1. Modular monolith in apps/api and apps/web: independent Python/Node dependency graphs and containers, shared product documentation.
2. PostgreSQL is authoritative. SQLAlchemy synchronous sessions keep critical transactions explicit. Alembic owns schema.
3. Opaque random server sessions, token hashes stored in database, HttpOnly SameSite=Lax cookies, session-bound CSRF header, exact Origin validation. No browser token persistence. Session expiry and ACTIVE status checked every request.
4. Owner/department manager/admin policy reused for lists, counts and every child resource. REVIEWER/APPROVER/LEGAL do not gain global access merely from their role.
5. PostgreSQL sequence allocates document numbers (gaps allowed); SELECT FOR UPDATE serializes document version and lifecycle writes. Current version is a constrained composite foreign key.
6. Private local storage behind an interface. Streaming bounded uploads, generated keys, exclusive creation, SHA-256, PDF/DOCX/TXT checks. A failed DB transaction removes the new file; crash recovery/orphan reconciliation remains future work.
7. Lifecycle supports draft submission, owner cancellation and terminal archiving; no approval decisions before Iteration 2.
8. Same-origin browser access through Next.js rewrite to API; API never exposes uploads as static resources.
9. AI, workflow and notifications are not implemented. Future workflow instances will bind immutable definition versions; deterministic backend rules own decisions.
