"""Operator authority changes tested only in the separate role-test database."""
import os
import subprocess

import psycopg
import pytest


def test_inspect_apply_disable_authority_registry():
    if os.environ.get('NEXORA_ISOLATED_ROLE_TEST') != 'isolated-docker-cluster':
        pytest.skip('Separate role-test cluster required')
    admin_url = os.environ['NEXORA_TEST_ADMIN_URL'].replace('postgresql+psycopg://', 'postgresql://')
    env = {**os.environ, 'NEXORA_ACL_OPERATOR_URL': os.environ['NEXORA_TEST_MIGRATIONS_URL']}
    args = ['python', '/ops/acl_authorities.py', '--user-id', 'owner', '--department-id', 'it', '--office',
            'CUSTODIAN', '--expires-at', '2099-01-01T00:00:00+00:00', '--reason', 'Synthetic operator verification']
    with psycopg.connect(admin_url) as conn:
        assert conn.info.dbname == 'nexora_test'
        assert conn.execute("SELECT count(*) FROM acl_authorities WHERE user_id='owner'").fetchone()[0] == 0
    result = subprocess.run(args, env=env, check=True, capture_output=True, text=True)
    assert 'inspect' in result.stdout
    with psycopg.connect(admin_url) as conn:
        assert conn.execute("SELECT count(*) FROM acl_authorities WHERE user_id='owner'").fetchone()[0] == 0
    subprocess.run([*args, '--apply'], env=env, check=True, capture_output=True)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute("SELECT active FROM acl_authorities WHERE user_id='owner'").fetchone()[0] is True
        assert conn.execute("SELECT count(*) FROM audit_events WHERE action='ACL_AUTHORITY_UPDATED'").fetchone()[0] == 1
    subprocess.run([*args, '--disable', '--apply'], env=env, check=True, capture_output=True)
    with psycopg.connect(admin_url) as conn:
        assert conn.execute("SELECT active FROM acl_authorities WHERE user_id='owner'").fetchone()[0] is False
    runtime_env = {**env, 'NEXORA_ACL_OPERATOR_URL': os.environ['NEXORA_TEST_DATABASE_URL']}
    denied = subprocess.run([*args, '--apply'], env=runtime_env, capture_output=True, text=True)
    assert denied.returncode != 0 and 'Only the dedicated migrations operator role' in denied.stderr
