# Database role separation — prepared, not applied to the existing database

## Plan

1. Record current DB/schema/object owners, grants, role flags, table counts and a verified backup.
2. Test first in a completely separate PostgreSQL instance, including an existing-data restore.
3. In an approved maintenance window stop API writes and backups; retain the old administrator credential outside API.
4. Run `ops/database_roles.py` using an administrator connection. Its default is inspection only. Applying requires an explicit target database confirmation. It creates three new, non-superuser login roles, transfers only NEXORA public-schema objects to migrations, removes PUBLIC schema creation, and grants explicit runtime operations and read-only backup privileges. Changes are one transaction.
5. Start API using `compose.roles.yaml` (also after the production overlay when applicable). Run migrations with the migrations credential, then reapply grants after migrations. API startup must not run Alembic. Backup uses its own read-only credential over TCP.
6. Verify login, uploads, document numbering, approval decisions, audit, sessions and dump/restore; compare record counts and blob hashes. Keep the existing administrator login for emergency operator use; do not put it in API.

The current database and running services are NOT switched by this work. Do not run any data-removal command or replace the existing volume.

## Roles

| Role | Purpose | Allowed | Denied |
|---|---|---|---|
| nexora_runtime | API and development seed | Explicit table operations; sequence USAGE; row/advisory locks | Ownership, DDL, TRUNCATE, sequence reset, role/database creation, SET ROLE migrations, update/delete immutable records |
| nexora_migrations | Alembic and operator restore into a precreated empty DB | Own public schema/tables/sequences/functions; schema DDL | SUPERUSER, CREATEROLE, CREATEDB, REPLICATION, BYPASSRLS |
| nexora_backup | pg_dump and read-only integrity queries | CONNECT, schema USAGE, SELECT tables/sequences | Writes, sequence allocation, DDL, TRUNCATE, role switching |

No runtime default privileges: new tables must be deliberately added to the grant allowlist. Backup SELECT defaults apply to objects subsequently created by migrations. This work does not add row-level security: backend document authorization remains unchanged.

## Rollback

Before applying, export owners/ACLs and keep the old Compose files and secret references. If provisioning fails its transaction rolls back. If cutover fails after provisioning, stop the new API, remove the roles overlay and restart using the old administrator connection. This restores connectivity without deleting data; keep new roles and ownership until investigated. To fully revert security configuration, an administrator restores the recorded owners/ACLs in a transaction, including schema ownership and default privileges. Do not drop roles with CASCADE and do not restore a dump over the live database. The old administrator remains able to service the DB throughout.

## Operator usage after approval

The provisioning script requires `NEXORA_ROLE_ADMIN_URL` (psycopg URL), and three distinct secrets: `DB_RUNTIME_PASSWORD`, `DB_MIGRATIONS_PASSWORD`, `DB_BACKUP_PASSWORD`. Role names are fixed, avoiding unsafe identifier interpolation. Never pass secrets as command-line arguments or commit them. URL passwords used by Compose must be percent-encoded; provisioning passwords are raw. Use different generated secrets for each role.

Inspection with pre-change metadata snapshot (private ignored path):

`python ops/database_roles.py --snapshot backups/role-owners-before.json`

Create the ignored backups directory first. Use an operator Python environment with psycopg installed; API dependencies already include it. The snapshot contains owners and ACLs, not passwords, and refuses overwrite.

Apply: `python ops/database_roles.py --apply --confirm-database <exact database name>`

The whole operation rolls back on error; DDL lock timeout is 5 seconds and each statement timeout is 60 seconds. Unexpected public-schema tables/sequences/functions and unmanaged role-name collisions are rejected. Existing database ownership and administrator role flags remain unchanged. No document records, numbering values, file bytes or table definitions are changed.

Compose opt-in: append `-f compose.roles.yaml` after the other selected overlays. Set `DB_RUNTIME_PASSWORD_URLENCODED`, `DB_MIGRATIONS_PASSWORD_URLENCODED` and `DB_BACKUP_PASSWORD` in the secret environment. Never use this overlay before role provisioning. For production, keep the security and production overlays. The overlay leaves DB configuration identical; backup injects its secret from the operator process without recreating PostgreSQL. Exact maintenance, fresh-restore state comparison and rollback commands are in `database-cutover.md`; historical backup results are in `backup-inventory.md`.

Restore is an administrator-approved operation into a NEW database, not a permission of the read-only backup role. The existing backup verifier retains that distinction. Runtime has no access to Alembic's version table.

Session revocation needs SELECT FOR UPDATE, which requires UPDATE on at least one column. Runtime receives UPDATE only for `auth_sessions.user_agent`, not session token hashes, CSRF, user identity or expiry. API functionality is unchanged. Existing explicit column grants are removed before applying the allowlist.

## Risks

- Ownership changes require a maintenance window; long transactions can delay DDL locks.
- Changing database PUBLIC CONNECT/TEMP affects other clients of that exact database; review clients first.
- Credentials are three independent secrets; runtime must not receive migration or administrator credentials.
- Future migrations require explicit grant review; intentional missing grants fail closed.
- Migrations can alter all NEXORA schema objects and triggers: that credential is privileged and must not be present in API.
- Backup can read all document/authentication data; protect both its credential and output.
- Production DB settings, pg_hba rules, password encoding and restore ownership must be tested in the actual environment before approval.

## Isolated verification (2026-10-08)

`ops/verify_database_roles.ps1` creates a separate PostgreSQL 17 instance on its own Docker network, with no working volumes or host ports. Source mounts are read-only and temporary passwords are generated in memory. It uses the existing development API image and checks migrations upgrade -> full downgrade -> upgrade, ruff/mypy, API regression under runtime, negative role permissions, transactional provisioning rollback, real backup-script archive bytes, and pg_dump/pg_restore.

`ops/verify_role_copy.py <isolated-db-container>` additionally reads a working dump and blobs, restores them into that separate instance, and compares all 17 tables before/after ownership changes. Login, document/workflow reads, four exact-byte/SHA-256 downloads and logout are tested through runtime on the COPY. It exercises the actual `ops/backup.py` utility on that copy and verifies every restored blob. Working table fingerprints are compared before and after the whole operation.

Observed results: 73 tests passed (31 existing, 31 role checks, 7 backup checks, 4 archive audit checks); no lint or mypy errors. Fresh migration cycle and migrations-owned restore passed without SUPERUSER. Existing-data copy preserved 7 users, 3 documents, 4 versions and the original 45 audit events. HTTP smoke intentionally adds login/download/logout audit events only to the copy; its verified backup contains 51 audit events. All four files passed size/SHA-256 validation. Working DB fingerprints were unchanged; no new dedicated role was applied to it. Development and production Compose merges validated, with API receiving only runtime credentials.

The archive regex defect found during this verification is corrected and covered by tests; see backup-restore.md. Old archives require independent verification before being used for rollback. A Starlette TestClient deprecation warning remains unrelated to this change.

The isolated containers and private ignored backup artifacts are retained for review. None of the working services was restarted or reconfigured. Preparation is published separately after security checks; this does not apply roles. Production cutover, downtime and actual production secret handling remain unperformed and require separate authorization.
