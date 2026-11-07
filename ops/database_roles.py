"""Explicit, transactional operator provisioning. Default: inspect, never apply."""

import argparse
import json
import os
from pathlib import Path

import psycopg
from psycopg import sql

ROLES = ("nexora_runtime", "nexora_migrations", "nexora_backup")
GRANTS = {
    "operation_keys": "SELECT, INSERT",
    "workflow_requirements": "SELECT",
    "acl_authorities": "SELECT",
    "acl_department_policies": "SELECT, INSERT, UPDATE",
    "access_grants": "SELECT, INSERT, UPDATE",
    "grant_endorsements": "SELECT, INSERT",
    "review_receipts": "SELECT, INSERT",
    "receipt_revocations": "SELECT, INSERT",
    "departments": "SELECT, INSERT",
    "users": "SELECT, INSERT, UPDATE",
    "document_types": "SELECT, INSERT, UPDATE",
    "documents": "SELECT, INSERT, UPDATE",
    "folders": "SELECT, INSERT, UPDATE",
    "document_favorites": "SELECT, INSERT, DELETE",
    "document_versions": "SELECT, INSERT",
    "comments": "SELECT, INSERT",
    "audit_events": "SELECT, INSERT",
    "workflow_templates": "SELECT, INSERT",
    "workflow_instances": "SELECT, INSERT, UPDATE",
    "approvals": "SELECT, INSERT, UPDATE",
    "workflow_events": "SELECT, INSERT",
    "file_scans": "SELECT, INSERT",
    "auth_sessions": "SELECT, INSERT, DELETE",
    # DELETE adds nothing beyond UPDATE (which can already reset failures) and lets the
    # runtime connection run `python -m app.auth_cleanup` for stale windows.
    "login_throttles": "SELECT, INSERT, UPDATE, DELETE",
}


def provision(conn, passwords):
    """Caller owns transaction; never commit partial grants or ownership changes."""
    conn.execute("SET LOCAL lock_timeout='5s'")
    conn.execute("SET LOCAL statement_timeout='60s'")
    database = conn.execute("SELECT current_database()").fetchone()[0]
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    ).fetchall()
    names = {row[0] for row in tables}
    if names - (set(GRANTS) | {"alembic_version"}):
        raise ValueError("Unexpected public-schema tables: review grants before applying")
    for role, password in zip(ROLES, passwords, strict=True):
        if len(password) < 20:
            raise ValueError("Use independent generated secrets of at least 20 characters")
        existing = conn.execute(
            "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname=%s", (role,)
        ).fetchone()
        marker = "NEXORA dedicated role: " + role
        if existing is not None and existing[0] != marker:
            raise ValueError("Role name collision: do not modify an unmanaged existing role")
        if existing is None:
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            conn.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(sql.Identifier(role), sql.Literal(marker)))
        # Refuse inherited privileges rather than silently changing unrelated memberships.
        if conn.execute(
            "SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=%s) "
            "OR roleid=(SELECT oid FROM pg_roles WHERE rolname=%s)", (role, role)
        ).fetchone():
            raise ValueError("Role memberships must be reviewed by an administrator")
        if conn.execute(
            "SELECT 1 FROM pg_database WHERE datdba=(SELECT oid FROM pg_roles WHERE rolname=%s)", (role,)
        ).fetchone():
            raise ValueError("Dedicated role must not own a database")
        conn.execute(sql.SQL(
            "ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
            "NOINHERIT LOGIN PASSWORD {}"
        ).format(sql.Identifier(role), sql.Literal(password)))
    if len(set(passwords)) != 3:
        raise ValueError("Role passwords must be distinct")
    conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(database)))
    for role in ROLES:
        conn.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM {}").format(
            sql.Identifier(database), sql.Identifier(role)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(role)))
    conn.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    conn.execute("ALTER SCHEMA public OWNER TO nexora_migrations")
    conn.execute("REVOKE ALL ON SCHEMA public FROM nexora_runtime, nexora_backup")
    conn.execute("GRANT USAGE ON SCHEMA public TO nexora_runtime, nexora_backup")
    for (name,) in tables:
        conn.execute(sql.SQL("ALTER TABLE public.{} OWNER TO nexora_migrations").format(sql.Identifier(name)))
    sequences = conn.execute("SELECT sequencename FROM pg_sequences WHERE schemaname='public'").fetchall()
    if {row[0] for row in sequences} - {"document_number_seq"}:
        raise ValueError("Unexpected public-schema sequences")
    for (name,) in sequences:
        conn.execute(sql.SQL("ALTER SEQUENCE public.{} OWNER TO nexora_migrations").format(sql.Identifier(name)))
    functions = conn.execute(
        "SELECT p.oid::regprocedure::text,p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname='public'"
    ).fetchall()
    if {row[1] for row in functions} - {"nexora_immutable_row", "nexora_workflow_snapshot", "nexora_acl_grant_snapshot",
                                         "nexora_operation_key_purge_guard"}:
        raise ValueError("Unexpected public-schema functions")
    # Function signatures come from the server catalog, never user input.
    for signature, _ in functions:
        conn.execute(sql.SQL("ALTER FUNCTION {} OWNER TO nexora_migrations").format(sql.SQL(signature)))
        conn.execute(sql.SQL("REVOKE ALL ON FUNCTION {} FROM PUBLIC, nexora_runtime, nexora_backup").format(
            sql.SQL(signature)))
    conn.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC, nexora_runtime, nexora_backup")
    # Table-level REVOKE does not remove previously granted column privileges.
    columns = conn.execute(
        "SELECT c.relname,a.attname FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
        "WHERE c.relnamespace='public'::regnamespace AND a.attnum>0 AND NOT a.attisdropped "
        "AND a.attacl IS NOT NULL"
    ).fetchall()
    for table, column in columns:
        conn.execute(sql.SQL("REVOKE ALL ({}) ON TABLE public.{} FROM PUBLIC, nexora_runtime, nexora_backup").format(
            sql.Identifier(column), sql.Identifier(table)))
    conn.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, nexora_runtime, nexora_backup")
    for name in sorted(names & set(GRANTS)):
        conn.execute(sql.SQL("GRANT {} ON TABLE public.{} TO nexora_runtime").format(
            sql.SQL(GRANTS[name]), sql.Identifier(name)))
    # SELECT FOR UPDATE needs UPDATE on at least one column. Do not grant token/identity mutation.
    if "auth_sessions" in names:
        conn.execute("GRANT UPDATE (user_agent) ON TABLE public.auth_sessions TO nexora_runtime")
    if sequences:
        conn.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO nexora_runtime")
    conn.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO nexora_backup")
    conn.execute("GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO nexora_backup")
    conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nexora_migrations IN SCHEMA public "
                 "REVOKE ALL ON TABLES FROM PUBLIC, nexora_runtime, nexora_backup")
    conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nexora_migrations IN SCHEMA public "
                 "REVOKE ALL ON SEQUENCES FROM PUBLIC, nexora_runtime, nexora_backup")
    conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nexora_migrations IN SCHEMA public "
                 "GRANT SELECT ON TABLES TO nexora_backup")
    conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nexora_migrations IN SCHEMA public "
                 "GRANT SELECT ON SEQUENCES TO nexora_backup")
    conn.execute("ALTER DEFAULT PRIVILEGES FOR ROLE nexora_migrations REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database")
    parser.add_argument("--snapshot", type=Path, help="Write pre-change owners and ACLs; refuses overwrite")
    args = parser.parse_args()
    with psycopg.connect(os.environ["NEXORA_ROLE_ADMIN_URL"]) as conn:
        database, admin = conn.execute("SELECT current_database(), current_user").fetchone()
        print("Target database:", database, "operator:", admin)
        if args.snapshot:
            queries = {
                "database": "SELECT datname,pg_get_userbyid(datdba),datacl::text FROM pg_database "
                            "WHERE datname=current_database()",
                "schema": "SELECT nspname,pg_get_userbyid(nspowner),nspacl::text FROM pg_namespace "
                          "WHERE nspname='public'",
                "relations": "SELECT relname,relkind,pg_get_userbyid(relowner),relacl::text FROM pg_class "
                             "WHERE relnamespace='public'::regnamespace ORDER BY relname",
                "functions": "SELECT oid::regprocedure::text,pg_get_userbyid(proowner),proacl::text FROM pg_proc "
                             "WHERE pronamespace='public'::regnamespace ORDER BY proname",
                "columns": "SELECT c.relname,a.attname,a.attacl::text FROM pg_attribute a "
                           "JOIN pg_class c ON c.oid=a.attrelid WHERE c.relnamespace='public'::regnamespace "
                           "AND a.attnum>0 AND NOT a.attisdropped AND a.attacl IS NOT NULL",
                "roles": "SELECT rolname,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                         "FROM pg_roles WHERE rolname IN (current_user,'nexora_runtime',"
                         "'nexora_migrations','nexora_backup')",
                "defaults": "SELECT pg_get_userbyid(defaclrole),defaclnamespace::regnamespace::text,"
                            "defaclobjtype,defaclacl::text FROM pg_default_acl",
            }
            snapshot = {key: conn.execute(query).fetchall() for key, query in queries.items()}
            with args.snapshot.open("x", encoding="utf-8") as output:
                json.dump(snapshot, output, indent=2)
        if not args.apply:
            print("Inspection only. No role, grant or ownership changes.")
            for row in conn.execute("SELECT schemaname,tablename,tableowner FROM pg_tables "
                                    "WHERE schemaname='public' ORDER BY tablename"):
                print(row)
            return
        if args.confirm_database != database:
            raise ValueError("Explicit exact database confirmation is required")
        provision(conn, [os.environ[key] for key in (
            "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD")])
    print("Committed role provisioning; API connection was not switched.")


if __name__ == "__main__":
    main()
