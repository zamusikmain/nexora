# Iteration 1 data model
Таблицы: departments, users, auth_sessions, login_throttles, document_types, documents, document_versions, comments, audit_events. Alembic добавляет alembic_version.
CHECK: user role/status, document status, positive version/size. UNIQUE: user email, department/type code, document number, storage key, (document_id,version_number), (document_id,id). Foreign keys связывают пользователей, подразделения, типы, документы, версии, авторов и actor. documents(id,current_version_id) -> document_versions(document_id,id), nullable до первой версии.
Sequence document_number_seq глобальная, не сбрасывается ежегодно; формат DOC-<UTC year>-<at least six digits>; пропуски при rollback допустимы. Версии выделяются под FOR UPDATE document lock с max existing version + 1; UNIQUE — дополнительная защита. PostgreSQL triggers запрещают UPDATE/DELETE versions и audit.
Indexes: user department; session user/expiry; document owner/type/department+status; version/comment document; audit action/target/time. Search ILIKE title/number, без fulltext/trigram/vector индексов.
JSON business_metadata — расширяемые domain fields; document_types.metadata_schema — extension point, не dynamic schema builder. Future workflow tables отсутствуют.
0001_core — explicit frozen migration с tables/constraints/indexes/sequence/triggers и reverse downgrade; runtime models не импортируются.
