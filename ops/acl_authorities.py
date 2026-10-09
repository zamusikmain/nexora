"""Operator-only business authority registry. Inspect by default; never an ADMIN API."""
import argparse
import json
import os
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--department-id', required=True)
    parser.add_argument('--office', required=True, choices=['CUSTODIAN', 'SECURITY'])
    parser.add_argument('--expires-at', required=True, help='Timezone-aware ISO date, stored in UTC')
    parser.add_argument('--reason', required=True)
    parser.add_argument('--disable', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    expires = datetime.fromisoformat(args.expires_at)
    if expires.tzinfo is None or (not args.disable and expires <= datetime.now(UTC)) or len(args.reason.strip()) < 3:
        parser.error('Future timezone-aware expiry and a business reason are required')
    # No default URL, passwords in arguments or environment-file fallback.
    url = os.environ['NEXORA_ACL_OPERATOR_URL'].replace('postgresql+psycopg://', 'postgresql://')
    with psycopg.connect(url) as conn:
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SET LOCAL statement_timeout='30s'")
        role = conn.execute('SELECT current_user').fetchone()[0]
        if role != 'nexora_migrations':
            raise RuntimeError('Only the dedicated migrations operator role may maintain business authorities')
        target = conn.execute('SELECT status FROM users WHERE id=%s FOR UPDATE', (args.user_id,)).fetchone()
        if not target or (not args.disable and target[0] != 'ACTIVE'):
            raise RuntimeError('An active existing user is required')
        if not conn.execute('SELECT 1 FROM departments WHERE id=%s', (args.department_id,)).fetchone():
            raise RuntimeError('Existing department required')
        old = conn.execute('SELECT id FROM acl_authorities WHERE user_id=%s AND department_id=%s AND office=%s FOR UPDATE',
                           (args.user_id, args.department_id, args.office)).fetchone()
        metadata = {'user_id': args.user_id, 'department_id': args.department_id, 'office': args.office,
                    'active': not args.disable, 'expires_at': expires.astimezone(UTC).isoformat(),
                    'reason': args.reason, 'operator_database_role': role}
        if not args.apply:
            print(json.dumps({'mode': 'inspect', **metadata}, ensure_ascii=False))
            conn.rollback()
            return
        authority_id = old[0] if old else str(uuid4())
        conn.execute('INSERT INTO acl_authorities(id,user_id,department_id,office,active,expires_at) VALUES (%s,%s,%s,%s,%s,%s) '
                     'ON CONFLICT (user_id,department_id,office) DO UPDATE SET active=EXCLUDED.active,expires_at=EXCLUDED.expires_at',
                     (authority_id, args.user_id, args.department_id, args.office, not args.disable, expires))
        conn.execute('INSERT INTO audit_events(id,actor_id,action,target_type,target_id,safe_metadata,request_id) '
                     'VALUES (%s,NULL,%s,%s,%s,%s,%s)', (str(uuid4()), 'ACL_AUTHORITY_UPDATED', 'acl_authority',
                                                        authority_id, Jsonb(metadata), str(uuid4())))
        print(json.dumps({'mode': 'applied', 'authority_id': authority_id}, ensure_ascii=False))


if __name__ == '__main__':
    main()
