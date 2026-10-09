"""Compare every row, including ACL history, after isolated pg_dump restoration."""
import os

import psycopg
from psycopg import sql


def run():
    if os.environ.get('NEXORA_ISOLATED_ROLE_TEST') != 'isolated-docker-cluster':
        raise RuntimeError('Separate test cluster required')
    url = os.environ['NEXORA_ROLE_ADMIN_URL']
    with psycopg.connect(url) as source, psycopg.connect(url.rsplit('/', 1)[0]+'/nexora_restore_test_roles') as restored:
        assert source.info.dbname == 'nexora_test'
        tables = source.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
        assert tables == restored.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
        for (name,) in tables:
            query = sql.SQL("SELECT count(*),md5(COALESCE(string_agg(to_jsonb(t)::text,'|' ORDER BY to_jsonb(t)::text),'')) FROM {} t").format(sql.Identifier(name))
            assert source.execute(query).fetchone() == restored.execute(query).fetchone(), name
        assert source.execute('SELECT last_value,is_called FROM document_number_seq').fetchone() == restored.execute(
            'SELECT last_value,is_called FROM document_number_seq').fetchone()
        print(f'ACL_RESTORE_EXACT_MATCH: {len(tables)} tables and numbering sequence', flush=True)


if __name__ == '__main__':
    run()
