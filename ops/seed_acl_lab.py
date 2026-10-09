"""Synthetic browser fixtures. Only an explicitly isolated nexora_test cluster."""
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import password_hasher
from app.models import AclAuthority, User

PASSWORD = "Test-only-password-2026"


def run():
    if os.environ.get('NEXORA_ISOLATED_ROLE_TEST') != 'isolated-docker-cluster':
        raise RuntimeError('Isolated marker required')
    engine = create_engine(os.environ['NEXORA_TEST_ADMIN_URL'])
    if engine.url.database != 'nexora_test':
        raise RuntimeError('Test database required')
    with Session(engine) as db, db.begin():
        for name, office in (('lab-custodian', 'CUSTODIAN'), ('lab-security', 'SECURITY')):
            db.add(User(id=name, email=name+'@test.local', display_name=name, role='USER', status='ACTIVE',
                        department_id='it', password_hash=password_hasher.hash(PASSWORD)))
            db.flush()
            db.add(AclAuthority(user_id=name, department_id='it', office=office, active=True,
                                expires_at=datetime.now(UTC)+timedelta(days=2)))

    def login(name):
        c = httpx.Client(base_url='http://api:8000/api/v1', headers={'origin': os.environ['WEB_ORIGIN']})
        r = c.post('/auth/login', json={'email': name+'@test.local', 'password': PASSWORD})
        assert r.status_code == 200, r.text
        c.headers['x-csrf-token'] = r.json()['csrf_token']
        return c

    owner, admin = login('owner'), login('admin')
    template = admin.post('/workflow-templates', json={'code': 'BROWSER_'+uuid4().hex[:8].upper(),
        'name_ru': 'ACL проверка', 'name_en': 'ACL review', 'stages': [
            {'name_ru': 'Юридическая проверка', 'name_en': 'Legal review', 'selector': 'user', 'targets': ['legal']},
            {'name_ru': 'Следующий этап', 'name_en': 'Next stage', 'selector': 'user', 'targets': ['stranger']}]})
    assert template.status_code == 201, template.text
    result = {}
    for label, classification in (('ordinary', 'INTERNAL'), ('restricted', 'RESTRICTED'), ('draft', 'INTERNAL')):
        r = owner.post('/documents', json={'title': 'Browser ACL '+label, 'type_id': 'type', 'confidentiality': classification})
        assert r.status_code == 201, r.text
        doc = r.json()
        base = '/documents/'+doc['id']
        r = owner.post(base+'/versions', files={'file': (label+'.txt', b'Synthetic browser ACL content', 'text/plain')})
        assert r.status_code == 201, r.text
        result[label] = {'document_id': doc['id'], 'version_id': r.json()['id']}
        if label != 'draft':
            r = owner.post(base+'/workflows', json={'template_id': template.json()['id'],
                'expected_revision': owner.get(base).json()['revision'], 'idempotency_key': str(uuid4())})
            assert r.status_code == 201, r.text
            result[label]['instance_id'] = r.json()['id']
            result[label]['approvals'] = {a['user_id']: a['id'] for a in r.json()['approvals']}
    print('SYNTHETIC_BROWSER_FIXTURES', result, flush=True)


if __name__ == '__main__':
    run()
