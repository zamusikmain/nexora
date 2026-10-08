"""Opt-in PostgreSQL negative privilege tests; disposable nexora_test DB only."""

import os

import psycopg
import pytest


@pytest.fixture
def role_connections():
    urls = [os.getenv(key) for key in (
        "NEXORA_TEST_DATABASE_URL", "NEXORA_TEST_MIGRATIONS_URL", "NEXORA_TEST_BACKUP_URL")]
    if not all(urls):
        pytest.skip("Set isolated runtime/migrations/backup connection URLs")
    connections = [psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://")) for url in urls]
    try:
        for conn in connections:
            assert conn.info.dbname == "nexora_test", "Never run role tests against a live database"
        yield connections
    finally:
        for conn in connections:
            conn.rollback()
            conn.close()


def test_role_attributes_and_ownership(role_connections):
    runtime, migrations, backup = role_connections
    for conn, name in zip(role_connections, (
        "nexora_runtime", "nexora_migrations", "nexora_backup"), strict=True):
        assert conn.execute("SELECT current_user").fetchone()[0] == name
        assert conn.execute(
            "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles "
            "WHERE rolname=current_user"
        ).fetchone() == (False,) * 5
    assert migrations.execute("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname='public'").fetchall() == [
        ("nexora_migrations",)]
    for conn in (runtime, backup):
        assert not conn.execute("SELECT has_schema_privilege(current_user,'public','CREATE')").fetchone()[0]
        assert not conn.execute("SELECT has_database_privilege(current_user,current_database(),'TEMP')").fetchone()[0]


@pytest.mark.parametrize("statement", [
    "CREATE TABLE public.forbidden_probe(id int)",
    "CREATE SCHEMA forbidden_probe",
    "CREATE TEMP TABLE forbidden_probe(id int)",
    "CREATE ROLE forbidden_probe",
    "CREATE DATABASE forbidden_probe",
    "ALTER TABLE documents ADD COLUMN forbidden_probe int",
    "ALTER TABLE audit_events DISABLE TRIGGER ALL",
    "TRUNCATE documents CASCADE",
    "UPDATE document_versions SET original_filename='forged' WHERE false",
    "DELETE FROM audit_events WHERE false",
    "UPDATE workflow_templates SET name_en='forged' WHERE false",
    "DELETE FROM workflow_events WHERE false",
    "UPDATE file_scans SET engine='forged' WHERE false",
    "SELECT setval('document_number_seq',1)",
    "SET ROLE nexora_migrations",
    "UPDATE alembic_version SET version_num='forged' WHERE false",
    "SELECT * FROM alembic_version",
    "SET session_replication_role='replica'",
    "UPDATE auth_sessions SET user_id='forged' WHERE false",
    "UPDATE auth_sessions SET csrf_token='forged' WHERE false",
])
def test_runtime_forbidden_statements(role_connections, statement):
    conn = role_connections[0]
    if statement.startswith("CREATE DATABASE"):
        # Otherwise PostgreSQL rejects the transaction context before checking CREATEDB.
        conn.rollback()
        conn.autocommit = True
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
    conn.rollback()


@pytest.mark.parametrize("statement", [
    "UPDATE users SET display_name='forged' WHERE false",
    "DELETE FROM auth_sessions WHERE false",
    "INSERT INTO departments(id,code,name_ru,name_en) VALUES ('probe','PROBE','x','x')",
    "SELECT nextval('document_number_seq')",
    "TRUNCATE audit_events",
    "CREATE TABLE public.forbidden_probe(id int)",
    "SET ROLE nexora_migrations",
])
def test_backup_is_read_only(role_connections, statement):
    conn = role_connections[2]
    assert conn.execute("SELECT count(*) FROM documents").fetchone()[0] >= 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(statement)
    conn.rollback()


def test_migrations_can_create_schema_objects(role_connections):
    conn = role_connections[1]
    conn.execute("CREATE TABLE public.migration_probe(id int)")
    conn.execute("ALTER TABLE public.migration_probe ADD COLUMN value text")
    conn.execute("DROP TABLE public.migration_probe")
    conn.rollback()


def test_no_runtime_grants_on_future_tables(role_connections):
    migrations = role_connections[1]
    migrations.execute("CREATE TABLE public.migration_probe(id int)")
    assert not migrations.execute(
        "SELECT has_table_privilege('nexora_runtime','public.migration_probe','SELECT')"
    ).fetchone()[0]
    assert migrations.execute(
        "SELECT has_table_privilege('nexora_backup','public.migration_probe','SELECT')"
    ).fetchone()[0]
    migrations.rollback()


def test_provisioning_rejection_rolls_back_all_changes(role_connections):
    # Run only in the opt-in isolated suite, with its separately supplied operator URL.
    admin_url = os.getenv("NEXORA_TEST_ADMIN_URL")
    if not admin_url or not os.getenv("NEXORA_ISOLATED_ROLE_TEST"):
        pytest.skip("Isolated operator connection required")
    from database_roles import provision

    with psycopg.connect(admin_url.replace("postgresql+psycopg://", "postgresql://")) as admin:
        assert admin.info.dbname == "nexora_test"
        owners_before = admin.execute(
            "SELECT tablename,tableowner FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ).fetchall()
        # Create a late validation failure, after ALTER ROLE/schema/table operations.
        admin.execute("CREATE FUNCTION public.unexpected_probe() RETURNS int LANGUAGE sql AS 'SELECT 1'")
        admin.execute("GRANT CREATE ON SCHEMA public TO nexora_runtime")
        admin.commit()
        try:
            with pytest.raises(ValueError, match="Unexpected public-schema functions"):
                with admin.transaction():
                    provision(admin, [os.environ[key] for key in (
                        "DB_RUNTIME_PASSWORD", "DB_MIGRATIONS_PASSWORD", "DB_BACKUP_PASSWORD")])
            assert owners_before == admin.execute(
                "SELECT tablename,tableowner FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            ).fetchall()
            assert admin.execute(
                "SELECT has_table_privilege('nexora_runtime','documents','UPDATE')"
            ).fetchone()[0]
            assert admin.execute(
                "SELECT has_schema_privilege('nexora_runtime','public','CREATE')"
            ).fetchone()[0], "Earlier REVOKE must have rolled back too"
        finally:
            admin.execute("DROP FUNCTION public.unexpected_probe()")
            admin.execute("REVOKE CREATE ON SCHEMA public FROM nexora_runtime")
            admin.commit()
