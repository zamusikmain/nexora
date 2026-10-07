# Implemented API
Base /api/v1. Mutations require exact WEB_ORIGIN; authenticated mutations also require X-CSRF-Token. No password hashes, session IDs or storage keys in public responses.

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

No empty workflow/approval/AI endpoints. Search is GET /documents.
Lifecycle: DRAFT/REVISION_REQUIRED -> SUBMITTED (requires file); DRAFT/SUBMITTED/REVISION_REQUIRED -> CANCELLED; CANCELLED/APPROVED/REJECTED -> ARCHIVED. Reserved future statuses cannot be directly set. Invalid transition 409; unsupported action/input 422.
