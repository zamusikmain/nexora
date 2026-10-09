# Implemented API
Base /api/v1. Mutations require exact WEB_ORIGIN; authenticated mutations also require X-CSRF-Token. No password hashes, cookie token hashes or storage keys in public responses. Session management uses independent public UUIDs.

| Methods | Path | Behavior |
|---|---|---|
| GET | /health, /ready | Liveness / DB readiness |
| POST | /auth/login | Local credentials, cookie, csrf_token |
| GET | /auth/me | ACTIVE session, public user, csrf_token |
| POST | /auth/logout | Revoke session |
| GET | /departments, /document-types | Authenticated RU/EN catalogs |
| GET | /users | ADMIN users |
| PATCH | /users/{id} | ADMIN role/status/department; self-change denied |
| GET | /documents | Visible list; q/status/type_id/department_id/page/page_size <=100 |
| POST | /documents | Actor-owned draft, actor department, sequence number |
| GET | /documents/{id} | Resource authorization |
| PATCH | /documents/{id} | Editable title/metadata only |
| POST | /documents/{id}/transitions | Owner/admin submit/cancel/archive |
| GET/POST | /documents/{id}/versions | Authorized list / upload |
| GET | /documents/{id}/versions/{version_id}/download | Document and version membership authorization |
| GET/POST | /documents/{id}/comments | Read / append unless archived |
| GET | /documents/{id}/activity | Latest 200 visible events |
| GET | /dashboard | Scoped counts/status/type/recent5 |
| GET | /audit | ADMIN paginated events, 50/page |

Workflow endpoints are implemented below. No AI/integration placeholder endpoints. Search is GET /documents.
Lifecycle: DRAFT/REVISION_REQUIRED -> SUBMITTED (requires file); DRAFT/SUBMITTED/REVISION_REQUIRED -> CANCELLED; CANCELLED/APPROVED/REJECTED -> ARCHIVED. Reserved future statuses cannot be directly set. Invalid transition 409; unsupported action/input 422.


## DMS increment (2026-10-07)
- GET /folders?parent_id= — visible direct children (bounded 200).
- POST /folders — name, optional parent_id. Private namespace of the actor.
- PATCH /folders/{id} — rename/move, owner or admin; cycle/depth checks.
- GET /folders/{id}/breadcrumbs — authorized ancestry.
- GET /documents adds view=all|my|favorites|archive|trash and folder_id. All results remain policy filtered and server paginated.
- POST /documents/{id}/move — folder_id, expected_revision.
- PUT/DELETE /documents/{id}/favorite — idempotent actor-specific favorites.
- POST /documents/{id}/trash and /restore — expected_revision; owner/admin, audited.
- POST /documents/{id}/versions/{version_id}/restore — expected_revision, creates new immutable version and blob.
- GET /documents/{id}/versions/{version_id}/diff/{other_id} — authorized bounded TXT unified diff (256KiB/2000 lines each).
- POST /document-types and PATCH /document-types/{id} — admin only; bilingual labels and up to 50 validated declarative fields. Existing type GET includes metadata_schema.fields.
- Document create/update now supports description, category, tags (30 x 50 chars), responsible_id, confidentiality, effective_date, expiration_date. Owner, department and lifecycle remain server controlled. Classification labels do not grant access.
- Document responses include folder_id, deleted_at and revision. New UI metadata writes send expected_revision; stale writes return 409 stale_document. Legacy PATCH without revision remains accepted for compatibility and is a known release limitation.
- Custom fields support text, textarea, number, date, timezone-aware datetime, boolean, select, multi-select, user, department, HTTP(S) URL; required/default/order/options/enabled/range/length. User/department references must exist; responsible user must be active. Dates must be ordered. No arbitrary regex, expression execution or URL fetching.
- Removing field keys from used types is rejected: disable fields to preserve historical values. Disabled historical values are retained.
- No physical purge endpoint is implemented; immutable versions and audit retain their protections.

## Workflow and security endpoints
- GET/POST /workflow-templates — authenticated latest versions / ADMIN creates immutable next version.
- GET/POST /documents/{id}/workflows — authorized history / owner-admin start with template_id, expected_revision, idempotency_key UUID.
- POST /workflows/{id}/decisions — approve/reject/revision/cancel, reason and idempotency_key; assigned pending actor only, owner/admin may cancel. Same actor/key/payload retry returns existing result; changed payload returns 409.
- GET /approvals?view=pending|completed|rejected|overdue — assigned actor's paginated work.
- GET /auth/sessions — own active sessions, public UUID/device/time/current flag.
- DELETE /auth/sessions/{id} — revoke own session, foreign UUID 404.
- POST /auth/sessions/revoke-others — preserve current session.
- POST /auth/users/{id}/sessions/revoke — ADMIN revokes target's sessions.
- GET /capabilities — authenticated actual scanner mode/development flag, no connection secrets.
Production downloads/submissions/workflow starts reject missing clean scan evidence. Scanner failures are 503 scanner_unavailable; detected malware 422 malware_detected; missing legacy scan 503 file_scan_required; byte corruption 503 file_unavailable.
# ACL Revision 2 candidate endpoints (not yet deployed)

All routes below are under `/api/v1`; mutating requests keep session Origin/CSRF checks. Technical ADMIN does not imply document read or business authority.

- `GET /access/people`: active organization directory (IDs/display names/departments, no credentials/document associations).
- `GET /access/authority`: caller's unexpired operator-managed business offices.
- `GET /access/grants?page=1`: only recipient/requester/owner/scoped office requests; frozen scope, status, endorsed offices, expiration. Expired grants deny reads immediately; this route also records expiration events.
- `POST /documents/{id}/access-requests`: owner or scoped custodian requests a personal/version-bound grant. `recipient_id`, `version_id`, `reason`, `hours`, `actions`; purposes `personal`, `review`, `audit_snapshot`, `incident`, with assignment binding for review/audit_snapshot.
- `POST /approvals/{id}/access-requests`: own current RESTRICTED task, or own stored snapshot; purpose `review` or `audit_snapshot`. Snapshot requests allow only the snapshot operation, no card/file.
- `POST /access/grants/{id}/endorse`: current scoped business office and exact `scope_hash`; distinct actors, no self endorsement. `POST /access/grants/{id}/revoke`: reason required.
- `PUT /departments/{id}/review-policy`: CUSTODIAN enables/disables ordinary draft handoff. `POST /documents/{id}/department-review`: owner hands a specific current version to the fixed current manager audience.
- `GET /approvals`: pending/overdue only own current stage; completed/rejected/cancelled lists contain own minimal receipts. `GET /approvals/{id}/review`: own current task or neutral access-required state, frozen card and pinned file only.
- `GET /approvals/{id}/receipt`: own minimal receipt plus permitted immutable own snapshot, never file permission. `POST /approvals/{id}/receipt/revoke`: scoped business authority; reason and optional complete hiding. Historical rows remain intact.
- Workflow decision responses for a participant contain their own receipt, not the full route. Owners retain the full route. Replaying the same decision key returns the corresponding immutable receipt.

See [policy matrix](acl-policy-revision-2.md), [implementation and limits](acl-implementation.md). Existing version/download/comment/activity/diff routes now authorize their individual resource; foreign/expired/revoked requests return 404.
