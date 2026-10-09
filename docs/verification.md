# NEXORA enterprise increment — verification

2026-10-08 candidate update: [ACL Revision 2 verification](acl-implementation.md) supersedes the ACL/read-policy and test-count statements below for the prepared working-tree code: 507 PASS, 0 XFAIL, isolated migration/copy/restore tests and RU/EN browser checks. Production remains on the previously deployed code/schema; the commercial readiness limitations remain.

2026-10-07. This report supersedes the historical Iteration 1/increment notes in [verification-history.md](verification-history.md). The entire commercial request is **PARTIALLY VERIFIED and incomplete**. Unimplemented modules below are not external blockers and are not claimed ready. No failing check is suppressed; configured final suites have zero skips.

| # | Deliverable | Status | Evidence and limits |
|---|---|---|---|
| 1 | Implementation | PARTIALLY VERIFIED | Private folders/breadcrumbs/moves, five document views, favorites, recoverable trash, structured metadata/custom types, immutable version restore/TXT diff; versioned workflow; antivirus/sessions/cleanup/recovery. Shared ACL/Recent/permanent purge absent. |
| 2 | Architecture | VERIFIED for implemented scope | Existing modular monolith preserved. PostgreSQL locks/constraints own concurrency; versioned workflow snapshots/events; fail-closed private file pipeline; runtime/development image separation. No tenant boundary. See decisions.md/workflows.md. |
| 3 | Migrations | VERIFIED | 0002_dms, 0003_metadata, 0004_workflows, 0005_scans, 0006_sessions appended after frozen 0001. Existing main upgraded; new nexora_clean_enterprise installs to 0006; Alembic check shows no drift. Disposable nexora_install_check downgrade to 0004/re-upgrade succeeds; earlier DMS downgrade/re-upgrade also tested. Never downgrade live data without recovery plan. |
| 4 | API | VERIFIED for exercised paths | Folder/favorite/trash/restore/type APIs; workflows/templates/decisions/approvals; capabilities and own/admin session revocation. docs/api.md enumerates actual paths and constraints. No fake AI/integration endpoints. |
| 5 | UI | PARTIALLY VERIFIED | Type/workflow builders, forms, folder navigation/views/actions, workflow history/decisions, My Approvals, Security and Sessions. User references still use IDs in some forms; full directory UX/shared folders absent. |
| 6 | Security controls | PARTIALLY VERIFIED | Existing Argon2/session/CSRF/Origin/RBAC preserved; real ClamAV quarantine/attestations, production fail-closed settings, download checksum, public-session UUID/revocation, safe orphan cleanup, non-root runtime images. No MFA/OIDC, dynamic ACL/revocation, production TLS/gateway review. |
| 7 | AI | NOT VERIFIED | No provider, parsing, RAG, citation or AI feature implemented. No simulated AI result. Missing provider credentials are not the sole reason: implementation itself is pending. |
| 8 | Integrations | NOT VERIFIED | No SMTP, signed webhooks, service accounts/tokens or external business integrations. Actual ClamAV scanner integration is verified separately under security. |
| 9 | Backend tests | VERIFIED | Final 31 passed, 0 failed, 0 skipped, PostgreSQL-backed API regression plus protocol/security/cleanup tests. Original 16 cases retained. One non-failing Starlette TestClient/httpx deprecation warning. |
| 10 | Frontend tests | VERIFIED with limited scope | 4/4 Node tests: RU/EN completeness, statuses/events, literal translation references, JSX prose localization. These are localization/static checks, not full component/browser E2E automation. |
| 11 | E2E | PARTIALLY VERIFIED | Real browser admin type/folder/custom-document creation, move/favorite/trash/restore; admin -> manager -> legal workflow reaches APPROVED. Actual HTTP antivirus upload rejection/download and restored API login/list/all-version download pass. No persisted automated browser suite/cross-browser coverage. |
| 12 | Lint/type/build | VERIFIED | Ruff check/format, mypy (20 app modules), ESLint, tsc, 4 frontend tests; Windows production build and latest Docker Next production build. Production API builds and pip check pass. SWC Windows sandbox restriction required an elevated build; no check disabled. |
| 13 | Docker | VERIFIED locally; production PARTIALLY VERIFIED | PostgreSQL/API/web/ClamAV all healthy, real running services at UI3300/API8800/PG55432, loopback ports. Three-file production Compose config validates; production image non-root uid10001, no tests/pytest/mypy/ruff/httpx. Actual HTTPS deployment/production secrets/provisioning not performed. |
| 14 | Backup/restore | VERIFIED for small snapshot | ops/backup.py creates dump+private files+SHA manifest without .env. Snapshot restored into a new DB: 2 docs/3 versions/35 audit/1 workflow/3 events; every referenced blob verified. Separate restored API at8890 upgraded schema, logged in, listed2 and downloaded all3 exact bytes/checksums; stopped afterwards. Production RPO/RTO, encrypted remote storage/escrow/scheduling/large recovery unverified. |
| 15 | Security regression | VERIFIED for tested controls | BOLA/session/Origin/CSRF, illegal transitions, immutable versions/audit/templates/events/snapshots/scan attestations, concurrency/idempotency, folder cycles, scan failures and legacy evidence, corrupted-file download refusal, foreign session IDs. Real ClamAV: clean accepted, EICAR blocked, unavailable scanner503, quarantine cleanup. Live HTTP clean+EICAR rejection audited and no extra version. Not a comprehensive penetration test. |
| 16 | Dependency audit | VERIFIED package checks, limited scope | Fresh pip-audit --strict of requirements.runtime.lock: no known vulnerabilities. npm audit --omit=dev:0. Full npm audit:5 high dev-chain findings (braces -> micromatch -> fast-glob -> Next ESLint plugin/config), GHSA-vfj7-8cjw-p6xm. Proposed force fix downgrades eslint-config-next14.2.35 and is not applied. Frontend standalone excludes this dev chain. Base-image OS vulnerabilities/SBOM not audited. |
| 17 | Performance | NOT VERIFIED at requested scale | Pagination/limits and visibility indexes exist; no 1k-user/50k-document/200k-version/500k-audit benchmark, p95 throughput target or EXPLAIN study. Test concurrency validates correctness only. |
| 18 | Browser QA | PARTIALLY VERIFIED | RU/EN, persisted language, selected owner/admin/manager/legal paths. Loaded document detail has no horizontal overflow at390/768/1280/1440/1900px; mobile screenshot saved. Session page renders own current session with RU/EN. Revocation correctness checked by API tests, not interactive browser action. Full WCAG, keyboard, all-page responsive and cross-browser coverage absent. |
| 19 | Git | VERIFIED local; push BLOCKED | Baseline059f7de, DMScb1d606, workflow776e0d8; security bd8fdea; recovery/report commit in git log. .env/backups/.tmp/venvs/dependencies/uploads/build outputs ignored. No remote configured, no push possible. |
| 20 | Remaining request | NOT VERIFIED | Tasks/mentions/watchers/notification outbox; company hierarchy/groups/invitations/granular permissions/delegation; MFA/OIDC; AI; fulltext/saved search/exports/advanced analytics; SMTP/webhooks/tokens; tenant isolation/org settings/plans; durable workers; complete accessibility/load/observability and commercial release QA. These are implementation gaps, not hidden failing tests or external-only blockers. |

## Important policy limits
Workflow participants retain related document read access, including current/future edits and all versions; no revocation or version-limited ACL exists. Classification is metadata only. Legacy metadata PATCH without expected_revision is accepted for Iteration 1 compatibility, so optimistic concurrency is not mandatory for every client. Folder namespace is private; no company folder permissions. Physical purge deliberately remains absent to preserve immutable history. Scan attestations are immutable and do not expire/rescan; asynchronous scanning is pending. API upload scanning is synchronous with a bounded deadline. See security.md before any sensitive pilot data.

## Reproducible checks
```powershell
docker compose -f compose.yaml -f compose.security.yaml config --quiet
docker compose -f compose.yaml -f compose.security.yaml up -d --build
docker compose exec api python -m ruff check app tests migrations
docker compose exec api python -m mypy app
docker compose exec api alembic check
# ONLY disposable database nexora_test; fixture deliberately rejects another name.
docker compose exec -e NEXORA_TEST_DATABASE_URL=postgresql+psycopg://nexora:local-development-only@db:5432/nexora_test api python -m pytest -q -o cache_dir=/tmp/nexora-pytest
# apps/web: npm run lint; npm run typecheck; npm run test; npm run build
# package audits: npm audit --omit=dev; npm audit; pip-audit -r requirements.runtime.lock --strict
# backup/recovery: see backup-restore.md
```
Unit run without the disposable DB explicitly skips integration tests and is not the verified full suite. Do not point the fixture at main data. Final working stack retains all original document versions and synthetic browser/antivirus QA data. Historical screenshots in ignored .tmp: nexora-dms-qa.png, nexora-workflow-qa.png, nexora-mobile-qa.png; latest release review screenshot is nexora-enterprise-qa.png.

## Resolved check failures
Earlier checks exposed a session-revocation NameError, a missing scan-existing import separator, duplicate translation key, retry-state ESLint issue, and production test contamination by development environment variables. Each was corrected and rerun. Latest suites pass without disabling checks. Known non-failing deprecation and dev dependency findings above remain visible.
