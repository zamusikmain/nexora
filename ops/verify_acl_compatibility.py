"""Old-schema synthetic copy: upgrade, lossless rollback and guarded rollback."""
import os

import psycopg
from alembic import command
from psycopg import sql


def verify(config, settings):
    if os.environ.get("NEXORA_ISOLATED_ROLE_TEST") != "isolated-docker-cluster":
        raise RuntimeError("Separate test cluster required")
    admin_url = os.environ["NEXORA_ROLE_ADMIN_URL"]
    migration_url = os.environ["NEXORA_TEST_MIGRATIONS_URL"]
    with psycopg.connect(admin_url) as conn:
        if conn.info.dbname != "nexora_test":
            raise RuntimeError("Test database required")
    settings.database_url = migration_url
    command.upgrade(config, "0006_sessions")
    with psycopg.connect(admin_url) as conn:
        conn.execute("INSERT INTO departments(id,code,name_ru,name_en) VALUES ('copy-dept','COPY','Копия','Copy')")
        conn.execute("INSERT INTO users(id,email,display_name,password_hash,role,status,department_id) "
                     "VALUES ('copy-user','copy@test.local','Synthetic owner','not-a-real-password','USER','ACTIVE','copy-dept')")
        conn.execute("INSERT INTO document_types(id,code,name_ru,name_en,metadata_schema) VALUES ('copy-type','COPY','Копия','Copy','{}')")
        conn.execute("INSERT INTO documents(id,number,title,type_id,owner_id,department_id,status,business_metadata) "
                     "VALUES ('copy-doc','COPY-1','Historical synthetic document','copy-type','copy-user','copy-dept','DRAFT','{}')")
        conn.execute("INSERT INTO document_versions(id,document_id,version_number,original_filename,storage_key,mime_type,size,sha256,created_by) "
                     "VALUES ('copy-version','copy-doc',1,'synthetic.txt',repeat('a',64),'text/plain',4,repeat('b',64),'copy-user')")
        conn.execute("UPDATE documents SET current_version_id='copy-version' WHERE id='copy-doc'")
        conn.execute("INSERT INTO comments(id,document_id,author_id,body) VALUES ('copy-comment','copy-doc','copy-user','Historical comment')")
        conn.execute("INSERT INTO audit_events(id,actor_id,action,target_type,target_id,safe_metadata,request_id) "
                     "VALUES ('copy-audit','copy-user','CREATED','document','copy-doc','{}','copy-request')")
        conn.execute("INSERT INTO workflow_templates(id,code,version,name_ru,name_en,definition,created_by) "
                     "VALUES ('copy-template','COPY',1,'История','History','{\"stages\":[]}','copy-user')")
        conn.execute("INSERT INTO workflow_instances(id,document_id,document_version_id,template_id,metadata_snapshot,stage,status,started_by,completed_at) "
                     "VALUES ('copy-process','copy-doc','copy-version','copy-template','{\"title\":\"Historical title\"}',0,'APPROVED','copy-user',now())")
        conn.execute("INSERT INTO approvals(id,instance_id,stage,user_id,status,acted_at) "
                     "VALUES ('copy-approval','copy-process',0,'copy-user','APPROVED',now())")
        conn.execute("INSERT INTO workflow_events(id,instance_id,actor_id,action,comment,previous_state,new_state,idempotency_key,request_hash) "
                     "VALUES ('copy-event','copy-process','copy-user','APPROVED','Historical own finding','RUNNING','APPROVED','copy-key',repeat('c',64))")
    with psycopg.connect(admin_url.rsplit('/', 1)[0] + '/postgres', autocommit=True) as conn:
        conn.execute("CREATE DATABASE nexora_test_acl_copy TEMPLATE nexora_test")
    copy_admin = admin_url.rsplit('/', 1)[0] + '/nexora_test_acl_copy'
    tables = ('departments', 'users', 'document_types', 'documents', 'document_versions', 'comments', 'audit_events',
              'workflow_templates', 'workflow_instances', 'approvals', 'workflow_events')

    def fingerprint():
        with psycopg.connect(copy_admin) as conn:
            result = {}
            for table in tables:
                excluded = ['metadata_snapshot'] if table == 'document_versions' else (
                    ['version_id', 'instance_id', 'stage'] if table == 'comments' else [])
                result[table] = conn.execute(sql.SQL(
                    "SELECT to_jsonb(t) - %s::text[] FROM {} t ORDER BY id"
                ).format(sql.Identifier(table)), (excluded,)).fetchall()
            return result

    before = fingerprint()
    settings.database_url = migration_url.rsplit('/', 1)[0] + '/nexora_test_acl_copy'
    command.upgrade(config, 'head')
    assert fingerprint() == before, 'Historical rows changed during upgrade'
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.access import receipt_data
    from app.models import Approval, Document, User, WorkflowInstance

    with Session(create_engine(copy_admin.replace('postgresql://', 'postgresql+psycopg://'))) as db:
        receipt = receipt_data(db, db.get(User, 'copy-user'), db.get(Approval, 'copy-approval'),
                               db.get(WorkflowInstance, 'copy-process'), db.get(Document, 'copy-doc'))
        assert receipt['outcome'] == 'APPROVED' and receipt['can_download'] is False
        assert 'snapshot' not in receipt and 'title' not in receipt
    command.downgrade(config, '0006_sessions')
    assert fingerprint() == before, 'Historical rows changed during rollback'
    command.upgrade(config, 'head')
    with psycopg.connect(copy_admin) as conn:
        conn.execute("INSERT INTO acl_authorities(id,user_id,department_id,office,active,expires_at) "
                     "VALUES ('copy-authority','copy-user','copy-dept','CUSTODIAN',true,now()+interval '1 day')")
    try:
        command.downgrade(config, '0006_sessions')
    except RuntimeError as error:
        assert 'rollback blocked' in str(error)
    else:
        raise AssertionError('Rollback must preserve new ACL records')
    assert fingerprint() == before
    with psycopg.connect(copy_admin) as conn:
        assert conn.execute("SELECT count(*) FROM acl_authorities").fetchone()[0] == 1
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone()[0] == '0007_acl'
    settings.database_url = migration_url
    command.downgrade(config, 'base')
    print('ACL_COPY_UPGRADE_ROLLBACK_AND_HISTORY_PASSED', flush=True)
