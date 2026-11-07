# API Specification — AS-IS

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

58 операций на 49 paths. [Raw OpenAPI 3.x](openapi/fastapi.openapi.json) получен app.openapi() без подключения к БД. [contract-notes](openapi/contract-notes.json) — дополнения из кода, не TO-BE и не изменение raw schema. Предлагаемых endpoints в поставке нет.

## Общий контракт

Cookie `nexora_session`, HttpOnly, SameSite=Lax, Secure вне development. Все операции кроме health/ready/login требуют current_user и ACTIVE. Mutating requests: точный Origin=WEB_ORIGIN и X-CSRF-Token из текущей сессии; login требует Origin, но не CSRF. Ошибки: JSON `{ "error": "code", "request_id": "uuid" }`; X-Request-ID в ответе. Обработчик RequestValidationError возвращает `validation_error`, а не стандартное FastAPI detail — это расхождение raw schema, GAP-003.

Idempotency-Key (UUID header) обязателен там, где handler вызывает begin. workflow start/decide используют UUID `idempotency_key` в JSON, а не обязательный header. Scope ключа — actor и namespace операций: повтор с другим payload/path →409. Replay снова проверяет права в handler; не является долгоживущим правом на документ. Нет TTL или автоматической очистки. PATCH карточки использует CAS и не begin; повтор со старым revision →409, а не replay. PUT/DELETE favorite естественно идемпотентны. Некоторые terminal revoke допускают повтор без нового аудита.

Валидация Pydantic: extra=forbid, длины/enum/ranges в components.schemas. Дополнительные DB/state/ACL проверки перечислены ниже. UUID path IDs в большинстве схем — bounded строки, не обещается общий UUID format. Success response с `additionalProperties=true` либо пустой schema — частично типизированный контракт: точная форма читается в serializer/handler, не придумана в OpenAPI. Для скачивания HTTP body — бинарный stream, JSON response schema raw не описывает его полностью.

Глобально возможны 401 (кроме публичных), 403 Origin/CSRF, 422 input, 413 body cap и 500 server_error. Список ошибок конкретного handler ниже не включает транзитивно все helper errors; полный каталог кодов в [ошибках](14-error-handling.md). Пагинация имеется только при параметре page; остальные коллекции могут иметь hard limit, описанный в authorization/business rules. Фильтры и constraints доступны в соответствующем объекте OpenAPI.

## Синтетические примеры

Запрос регистрации (existing synthetic type_id подразумевается, не запись реальной БД):

```json
{"title":"Учебная записка","type_id":"demo-type","confidentiality":"INTERNAL","business_metadata":{}}
```

Полный пример DocumentOut для только что созданной карточки, значения иллюстративные:

```json
{"id":"demo-document","number":"DOC-2026-000001","title":"Учебная записка","type_id":"demo-type","owner_id":"demo-owner","department_id":"demo-dept","status":"DRAFT","revision":1,"current_version_id":null,"folder_id":null,"deleted_at":null,"description":"","category":"","tags":[],"responsible_id":null,"confidentiality":"INTERNAL","effective_date":null,"expiration_date":null,"business_metadata":{},"created_at":"2026-10-11T00:00:00Z","updated_at":"2026-10-11T00:00:00Z","capabilities":{}}
```

PATCH: `{"expected_revision":1,"title":"Уточнённая записка"}`. Start: `{"template_id":"demo-template","expected_revision":2,"idempotency_key":"11111111-1111-4111-8111-111111111111"}`. Decision: `{"action":"revision","comment":"Нужно уточнение","idempotency_key":"22222222-2222-4222-8222-222222222222"}`. Error: `{"error":"stale_document","request_id":"33333333-3333-4333-8333-333333333333"}`. Upload — multipart file + change_note, не JSON. Эти примеры не предназначены для выполнения на рабочей среде.

## Операции

### API-001 — GET /api/v1/health

Purpose: Проверить, что API отвечает.

- Authentication: Публичная операция.
- Authorization / Business rules: Публично, без проверки зависимостей.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"additionalProperties": true, "type": "object", "title": "Response Health Api V1 Health Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/main.py:78](../../apps/api/app/main.py#L78).

### API-002 — GET /api/v1/ready

Purpose: Проверить доступность PostgreSQL.

- Authentication: Публичная операция.
- Authorization / Business rules: Публично; SELECT 1, 503 при ошибке БД.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"additionalProperties": true, "type": "object", "title": "Response Ready Api V1 Ready Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 503 `'database_unavailable'`
- Code reference: [apps/api/app/main.py:83](../../apps/api/app/main.py#L83).

### API-003 — GET /api/v1/capabilities

Purpose: Получить режим scanner/development.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: любая ACTIVE сессия.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/main.py:102](../../apps/api/app/main.py#L102).

### API-004 — POST /api/v1/auth/login

Purpose: Войти по локальным credentials.

- Authentication: Публичная операция.
- Authorization / Business rules: Без сессии; точный Origin на POST; ACTIVE credentials и throttle.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: application/json: `{"$ref": "#/components/schemas/Login"}`
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/SessionOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 429 `'login_rate_limited'`; 401 `'invalid_credentials'`
- Code reference: [apps/api/app/auth.py:61](../../apps/api/app/auth.py#L61).

### API-005 — GET /api/v1/auth/me

Purpose: Получить текущую сессию и CSRF.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: собственная сессия; csrf token отдаётся для subsequent requests.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/SessionOut"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/auth.py:136](../../apps/api/app/auth.py#L136).

### API-006 — POST /api/v1/auth/logout

Purpose: Завершить текущую сессию.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: собственная сессия; удаление cookie и аудит.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 204: 
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/auth.py:141](../../apps/api/app/auth.py#L141).

### API-007 — GET /api/v1/auth/sessions

Purpose: Перечислить свои активные сессии.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только свои ACTIVE sessions, максимум 20; public_id.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"additionalProperties": true, "type": "object"}, "type": "array", "title": "Response Sessions Api V1 Auth Sessions Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/auth.py:149](../../apps/api/app/auth.py#L149).

### API-008 — POST /api/v1/auth/sessions/revoke-others

Purpose: Отозвать остальные собственные сессии.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: собственные остальные sessions.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 204: 
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/auth.py:169](../../apps/api/app/auth.py#L169).

### API-009 — DELETE /api/v1/auth/sessions/{session_id}

Purpose: Отозвать свою сессию по public_id.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только собственная session по public_id; чужая 404.
- Path/query parameters и declarative validation: path `session_id` required=True schema=`{"type": "string", "title": "Session Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 204: ; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/auth.py:180](../../apps/api/app/auth.py#L180).

### API-010 — POST /api/v1/auth/users/{user_id}/sessions/revoke

Purpose: Отозвать сессии пользователя администратором.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN; target существует.
- Path/query parameters и declarative validation: path `user_id` required=True schema=`{"type": "string", "title": "User Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 204: ; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/auth.py:197](../../apps/api/app/auth.py#L197).

### API-011 — GET /api/v1/documents

Purpose: Получить доступный реестр с фильтрами и поиском.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: SQL visibility; нет blanket ADMIN; фильтры не обходят ACL.
- Path/query parameters и declarative validation: query `q` required=False schema=`{"type": "string", "maxLength": 240, "default": "", "title": "Q"}`; query `view` required=False schema=`{"type": "string", "pattern": "^(all|my|favorites|archive|trash)$", "default": "all", "title": "View"}`; query `folder_id` required=False schema=`{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Folder Id"}`; query `status` required=False schema=`{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Status"}`; query `type_id` required=False schema=`{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Type Id"}`; query `department_id` required=False schema=`{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Department Id"}`; query `page` required=False schema=`{"type": "integer", "minimum": 1, "default": 1, "title": "Page"}`; query `page_size` required=False schema=`{"type": "integer", "maximum": 100, "minimum": 1, "default": 25, "title": "Page Size"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/DocumentListOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: page offset; page_size если объявлен; см. parameter defaults.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/documents.py:144](../../apps/api/app/documents.py#L144).

### API-012 — POST /api/v1/documents

Purpose: Зарегистрировать карточку документа.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: Любая ACTIVE роль с create; owner/dept берутся из user.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: application/json: `{"$ref": "#/components/schemas/DocumentCreate"}`
- Response schema / declared statuses: 201: application/json `{"$ref": "#/components/schemas/DocumentOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 422 `'invalid_document_type'`
- Code reference: [apps/api/app/documents.py:214](../../apps/api/app/documents.py#L214).

### API-013 — GET /api/v1/documents/{doc_id}

Purpose: Прочитать разрешённую проекцию карточки.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: card visibility; frozen projection для участника/grant.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/DocumentOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/documents.py:241](../../apps/api/app/documents.py#L241).

### API-014 — PATCH /api/v1/documents/{doc_id}

Purpose: Частично изменить карточку с CAS.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner, editable, не trash; expected_revision; RESTRICTED downgrade запрещён.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/DocumentUpdate"}`
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/DocumentOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'stale_document'`; 422 `'invalid_document_type'`; 403 `'classification_change_forbidden'`; 422 `'invalid_dates'`
- Code reference: [apps/api/app/documents.py:246](../../apps/api/app/documents.py#L246).

### API-015 — POST /api/v1/documents/{doc_id}/transitions

Purpose: Отправить, отменить вне workflow или архивировать.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner, не trash; submit/cancel/archive по допустимым source states; submit требует файл/scan.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Transition"}`
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/DocumentOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 403 `'forbidden'`; 409 `'document_in_trash'`; 409 `'invalid_transition'`; 409 `'file_required'`
- Code reference: [apps/api/app/documents.py:280](../../apps/api/app/documents.py#L280).

### API-016 — GET /api/v1/documents/{doc_id}/versions

Purpose: Перечислить разрешённые версии.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: card доступ плюс file action отдельно для каждой версии.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "array", "items": {"$ref": "#/components/schemas/VersionOut"}, "title": "Response Versions Api V1 Documents  Doc Id  Versions Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/documents.py:318](../../apps/api/app/documents.py#L318).

### API-017 — POST /api/v1/documents/{doc_id}/versions

Purpose: Загрузить и проверить новую версию файла.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner, editable, не trash; file validation и scanner.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: multipart/form-data: `{"$ref": "#/components/schemas/Body_upload_version_api_v1_documents__doc_id__versions_post"}`
- Response schema / declared statuses: 201: application/json `{"$ref": "#/components/schemas/VersionOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 413 `'file_too_large'`; 404 `'not_found'`
- Code reference: [apps/api/app/documents.py:347](../../apps/api/app/documents.py#L347).

### API-018 — GET /api/v1/documents/{doc_id}/versions/{version_id}/download

Purpose: Скачать разрешённый приватный файл.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: file action конкретной версии, принадлежащей doc; scan/checksum; audit.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`; path `version_id` required=True schema=`{"type": "string", "title": "Version Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 503 `'file_unavailable'`; 503 `'file_unavailable'`; 503 `'file_unavailable'`
- Code reference: [apps/api/app/documents.py:416](../../apps/api/app/documents.py#L416).

### API-019 — GET /api/v1/documents/{doc_id}/comments

Purpose: Прочитать разрешённый поток комментариев.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner или текущий review: только его stage/version; иначе comments grant текущей версии.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "array", "items": {"$ref": "#/components/schemas/CommentOut"}, "title": "Response Comments Api V1 Documents  Doc Id  Comments Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/documents.py:464](../../apps/api/app/documents.py#L464).

### API-020 — POST /api/v1/documents/{doc_id}/comments

Purpose: Добавить scoped комментарий.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: card + comment permission; owner/active review/explicit comments grant; не archive/trash.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/CommentCreate"}`
- Response schema / declared statuses: 201: application/json `{"$ref": "#/components/schemas/CommentOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'document_not_editable'`; 404 `'not_found'`
- Code reference: [apps/api/app/documents.py:485](../../apps/api/app/documents.py#L485).

### API-021 — GET /api/v1/documents/{doc_id}/activity

Purpose: Прочитать разрешённую историю документа.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: history action; foreign events дополнительно по version_id текущей версии.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "array", "items": {"type": "object", "additionalProperties": true}, "title": "Response Activity Api V1 Documents  Doc Id  Activity Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/documents.py:512](../../apps/api/app/documents.py#L512).

### API-022 — GET /api/v1/departments

Purpose: Получить справочник отделов.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: любая ACTIVE сессия; общий справочник.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"additionalProperties": true, "type": "object"}, "type": "array", "title": "Response Departments Api V1 Departments Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/catalog.py:16](../../apps/api/app/catalog.py#L16).

### API-023 — GET /api/v1/document-types

Purpose: Получить типы документов и custom-field schemas.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: любая ACTIVE сессия; общий справочник типов.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"additionalProperties": true, "type": "object"}, "type": "array", "title": "Response Types Api V1 Document Types Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/catalog.py:24](../../apps/api/app/catalog.py#L24).

### API-024 — GET /api/v1/users

Purpose: Получить пользователей для администрирования.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN; до 500 записей, без password_hash.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"$ref": "#/components/schemas/UserOut"}, "type": "array", "title": "Response Users Api V1 Users Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/catalog.py:39](../../apps/api/app/catalog.py#L39).

### API-025 — PATCH /api/v1/users/{user_id}

Purpose: Изменить роль, статус или отдел с CAS.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN; нельзя менять себя; CAS expected_updated_at.
- Path/query parameters и declarative validation: path `user_id` required=True schema=`{"type": "string", "title": "User Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/UserUpdate"}`
- Response schema / declared statuses: 200: application/json `{"$ref": "#/components/schemas/UserOut"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'self_admin_change'`; 404 `'not_found'`; 409 `'stale_record'`; 422 `'invalid_department'`
- Code reference: [apps/api/app/catalog.py:45](../../apps/api/app/catalog.py#L45).

### API-026 — GET /api/v1/dashboard

Purpose: Получить агрегаты и свежие разрешённые документы.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: SQL visibility и frozen title/status; только доступные карточки.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"additionalProperties": true, "type": "object", "title": "Response Dashboard Api V1 Dashboard Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/catalog.py:74](../../apps/api/app/catalog.py#L74).

### API-027 — GET /api/v1/audit

Purpose: Получить ограниченный административный аудит.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN audit; document events только owner, остальные target types доступны.
- Path/query parameters и declarative validation: query `page` required=False schema=`{"type": "integer", "minimum": 1, "default": 1, "title": "Page"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Audit Events Api V1 Audit Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: page offset; page_size если объявлен; см. parameter defaults.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/catalog.py:93](../../apps/api/app/catalog.py#L93).

### API-028 — POST /api/v1/document-types

Purpose: Создать тип документа.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN; валидная metadata schema и уникальный code.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: application/json: `{"$ref": "#/components/schemas/TypeInput"}`
- Response schema / declared statuses: 201: application/json `{"additionalProperties": true, "type": "object", "title": "Response Create Type Api V1 Document Types Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'duplicate_code'`
- Code reference: [apps/api/app/catalog.py:124](../../apps/api/app/catalog.py#L124).

### API-029 — PATCH /api/v1/document-types/{type_id}

Purpose: Изменить тип документа и metadata schema.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN; CAS expected_updated_at, проверка влияния schema.
- Path/query parameters и declarative validation: path `type_id` required=True schema=`{"type": "string", "title": "Type Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/TypeUpdate"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Update Type Api V1 Document Types  Type Id  Patch"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 409 `'stale_record'`; 409 `'field_in_use'`; 409 `'duplicate_code'`
- Code reference: [apps/api/app/catalog.py:150](../../apps/api/app/catalog.py#L150).

### API-030 — POST /api/v1/documents/{doc_id}/access-requests

Purpose: Запросить персональный допуск к версии.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner либо действующий CUSTODIAN отдела; scope фиксируется.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/GrantInput"}`
- Response schema / declared statuses: 201: application/json `{"type": "object", "additionalProperties": true, "title": "Response Create Grant Api V1 Documents  Doc Id  Access Requests Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/access.py:187](../../apps/api/app/access.py#L187).

### API-031 — POST /api/v1/approvals/{approval_id}/access-requests

Purpose: Запросить собственный review/snapshot допуск RESTRICTED.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только собственное назначение RESTRICTED; review/audit_snapshot и ограниченные actions.
- Path/query parameters и declarative validation: path `approval_id` required=True schema=`{"type": "string", "title": "Approval Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/OwnAccessInput"}`
- Response schema / declared statuses: 201: application/json `{"type": "object", "additionalProperties": true, "title": "Response Request Own Access Api V1 Approvals  Approval Id  Access Requests Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 422 `'invalid_grant_actions'`
- Code reference: [apps/api/app/access.py:202](../../apps/api/app/access.py#L202).

### API-032 — GET /api/v1/access/grants

Purpose: Перечислить доступные запросы и допуски.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: получатель/requester/owner/действующий office; GET материализует до 100 истёкших grants с аудитом.
- Path/query parameters и declarative validation: query `page` required=False schema=`{"type": "integer", "minimum": 1, "default": 1, "title": "Page"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Grants Api V1 Access Grants Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: page offset; page_size если объявлен; см. parameter defaults.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/access.py:229](../../apps/api/app/access.py#L229).

### API-033 — POST /api/v1/access/grants/{grant_id}/endorse

Purpose: Подтвердить scope допуска своим office.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: действующий указанный office; actor != requester/recipient/предыдущий voter; scope_hash.
- Path/query parameters и declarative validation: path `grant_id` required=True schema=`{"type": "string", "title": "Grant Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/EndorseInput"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Endorse Api V1 Access Grants  Grant Id  Endorse Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 404 `'not_found'`; 403 `'self_approval_forbidden'`; 409 `'grant_scope_changed'`; 409 `'grant_not_pending'`; 409 `'grant_scope_changed'`; 409 `'grant_scope_changed'`; 409 `'duplicate_endorsement'`; 403 `'forbidden'`; 409 `'approval_not_active'`; 409 `'grant_scope_changed'`
- Code reference: [apps/api/app/access.py:254](../../apps/api/app/access.py#L254).

### API-034 — POST /api/v1/access/grants/{grant_id}/revoke

Purpose: Отозвать/отклонить допуск.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: visible_grant: requester/recipient/owner либо действующее office.
- Path/query parameters и declarative validation: path `grant_id` required=True schema=`{"type": "string", "title": "Grant Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/RevokeInput"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Revoke Api V1 Access Grants  Grant Id  Revoke Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 404 `'not_found'`
- Code reference: [apps/api/app/access.py:308](../../apps/api/app/access.py#L308).

### API-035 — PUT /api/v1/departments/{department_id}/review-policy

Purpose: Настроить opt-in review policy отдела.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только действующий CUSTODIAN отдела.
- Path/query parameters и declarative validation: path `department_id` required=True schema=`{"type": "string", "title": "Department Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/ReviewPolicyInput"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Review Policy Api V1 Departments  Department Id  Review Policy Put"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/access.py:326](../../apps/api/app/access.py#L326).

### API-036 — POST /api/v1/documents/{doc_id}/department-review

Purpose: Передать текущий черновик текущим MANAGER отдела.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner, policy enabled, same dept MANAGER, PUBLIC/INTERNAL, editable current version.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/DraftShareInput"}`
- Response schema / declared statuses: 201: application/json `{"type": "object", "additionalProperties": true, "title": "Response Share Draft Api V1 Documents  Doc Id  Department Review Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 409 `'department_review_disabled'`; 422 `'invalid_grant_target'`
- Code reference: [apps/api/app/access.py:340](../../apps/api/app/access.py#L340).

### API-037 — POST /api/v1/approvals/{approval_id}/receipt/revoke

Purpose: Отозвать snapshot или скрыть receipt.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: действующий CUSTODIAN или SECURITY отдела; hide_receipt опционален.
- Path/query parameters и declarative validation: path `approval_id` required=True schema=`{"type": "string", "title": "Approval Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/RevokeInput"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Revoke Receipt Api V1 Approvals  Approval Id  Receipt Revoke Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 404 `'not_found'`; 409 `'receipt_already_revoked'`
- Code reference: [apps/api/app/access.py:367](../../apps/api/app/access.py#L367).

### API-038 — GET /api/v1/approvals/{approval_id}/receipt

Purpose: Прочитать собственную квитанцию и разрешённый снимок.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только своё решение; revocation/snapshot условия; никогда file.
- Path/query parameters и declarative validation: path `approval_id` required=True schema=`{"type": "string", "title": "Approval Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Receipt Api V1 Approvals  Approval Id  Receipt Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/access.py:421](../../apps/api/app/access.py#L421).

### API-039 — GET /api/v1/access/people

Purpose: Получить каталог активных сотрудников.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: любая ACTIVE сессия, организационный каталог до 500 ACTIVE лиц, без паролей.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"additionalProperties": true, "type": "object"}, "type": "array", "title": "Response People Api V1 Access People Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/access.py:433](../../apps/api/app/access.py#L433).

### API-040 — GET /api/v1/access/authority

Purpose: Получить собственные действующие offices.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только собственные действующие offices.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"additionalProperties": true, "type": "object"}, "type": "array", "title": "Response Own Authority Api V1 Access Authority Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/access.py:440](../../apps/api/app/access.py#L440).

### API-041 — GET /api/v1/folders

Purpose: Получить личные дочерние папки.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только owner дерева; parent_id проверяется.
- Path/query parameters и declarative validation: query `parent_id` required=False schema=`{"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Parent Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "array", "items": {"type": "object", "additionalProperties": true}, "title": "Response Folders Api V1 Folders Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/dms.py:71](../../apps/api/app/dms.py#L71).

### API-042 — GET /api/v1/folders/{folder_id}/breadcrumbs

Purpose: Получить путь личной папки.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только owner всех ancestors; максимум depth 32.
- Path/query parameters и declarative validation: path `folder_id` required=True schema=`{"type": "string", "title": "Folder Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "array", "items": {"type": "object", "additionalProperties": true}, "title": "Response Breadcrumbs Api V1 Folders  Folder Id  Breadcrumbs Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'folder_depth'`
- Code reference: [apps/api/app/dms.py:80](../../apps/api/app/dms.py#L80).

### API-043 — POST /api/v1/folders

Purpose: Создать личную папку.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: личное дерево; owner lock, depth <=32.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: application/json: `{"$ref": "#/components/schemas/FolderInput"}`
- Response schema / declared statuses: 201: application/json `{"type": "object", "additionalProperties": true, "title": "Response Create Folder Api V1 Folders Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 403 `'forbidden'`; 409 `'folder_depth'`
- Code reference: [apps/api/app/dms.py:93](../../apps/api/app/dms.py#L93).

### API-044 — PATCH /api/v1/folders/{folder_id}

Purpose: Переименовать или переместить папку с CAS.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner, expected_updated_at; owner lock, no cycle/depth overflow.
- Path/query parameters и declarative validation: path `folder_id` required=True schema=`{"type": "string", "title": "Folder Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/FolderUpdate"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Move Folder Api V1 Folders  Folder Id  Patch"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'stale_record'`; 403 `'forbidden'`; 409 `'folder_cycle'`; 409 `'folder_depth'`
- Code reference: [apps/api/app/dms.py:114](../../apps/api/app/dms.py#L114).

### API-045 — POST /api/v1/documents/{doc_id}/move

Purpose: Переместить документ в свою папку с CAS.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner editable; expected_revision; только собственная папка.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Move"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Move Document Api V1 Documents  Doc Id  Move Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 403 `'forbidden'`
- Code reference: [apps/api/app/dms.py:148](../../apps/api/app/dms.py#L148).

### API-046 — PUT /api/v1/documents/{doc_id}/favorite

Purpose: Добавить доступный документ в своё избранное.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: card доступ; только собственная favorite relation.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 204: ; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/dms.py:166](../../apps/api/app/dms.py#L166).

### API-047 — DELETE /api/v1/documents/{doc_id}/favorite

Purpose: Удалить документ из своего избранного.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: card доступ; только собственная favorite relation.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 204: ; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/dms.py:173](../../apps/api/app/dms.py#L173).

### API-048 — POST /api/v1/documents/{doc_id}/trash

Purpose: Поместить документ в корзину без удаления bytes.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner; CAS, правила состояния в handler, soft delete.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Revision"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Trash Api V1 Documents  Doc Id  Trash Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'invalid_transition'`
- Code reference: [apps/api/app/dms.py:182](../../apps/api/app/dms.py#L182).

### API-049 — POST /api/v1/documents/{doc_id}/restore

Purpose: Восстановить документ из корзины.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner; CAS; только trash.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Revision"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Restore Document Api V1 Documents  Doc Id  Restore Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 409 `'invalid_transition'`
- Code reference: [apps/api/app/dms.py:204](../../apps/api/app/dms.py#L204).

### API-050 — POST /api/v1/documents/{doc_id}/versions/{version_id}/restore

Purpose: Восстановить старую версию в новый immutable blob.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner editable; CAS; исходная версия в doc; новый blob и scan.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`; path `version_id` required=True schema=`{"type": "string", "title": "Version Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Revision"}`
- Response schema / declared statuses: 201: application/json `{"type": "object", "additionalProperties": true, "title": "Response Restore Version Api V1 Documents  Doc Id  Versions  Version Id  Restore Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 503 `'file_unavailable'`; 503 `'file_unavailable'`
- Code reference: [apps/api/app/dms.py:220](../../apps/api/app/dms.py#L220).

### API-051 — GET /api/v1/documents/{doc_id}/versions/{version_id}/diff/{other_id}

Purpose: Сравнить две разрешённые TXT версии.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: card + file и compare для обеих версий; TXT <=256KiB и <=2000 lines.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`; path `version_id` required=True schema=`{"type": "string", "title": "Version Id"}`; path `other_id` required=True schema=`{"type": "string", "title": "Other Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Diff Api V1 Documents  Doc Id  Versions  Version Id  Diff  Other Id  Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 422 `'diff_unsupported'`; 404 `'not_found'`; 422 `'diff_unsupported'`; 503 `'file_unavailable'`; 503 `'file_unavailable'`
- Code reference: [apps/api/app/dms.py:295](../../apps/api/app/dms.py#L295).

### API-052 — GET /api/v1/workflow-templates

Purpose: Получить последние версии шаблонов.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: любая ACTIVE сессия; последние версии по code (до 100).
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"items": {"additionalProperties": true, "type": "object"}, "type": "array", "title": "Response Templates Api V1 Workflow Templates Get"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/workflows.py:121](../../apps/api/app/workflows.py#L121).

### API-053 — POST /api/v1/workflow-templates

Purpose: Создать новую версию шаблона.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: ADMIN; selectors/targets валидны; новая immutable версия.
- Path/query parameters и declarative validation: Отсутствуют.
- Request body: application/json: `{"$ref": "#/components/schemas/TemplateInput"}`
- Response schema / declared statuses: 201: application/json `{"additionalProperties": true, "type": "object", "title": "Response Create Template Api V1 Workflow Templates Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID header Idempotency-Key обязателен; durable operation_keys.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 422 `'invalid_workflow_target'`
- Code reference: [apps/api/app/workflows.py:143](../../apps/api/app/workflows.py#L143).

### API-054 — GET /api/v1/documents/{doc_id}/workflows

Purpose: Прочитать процессы собственного документа.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только owner; не все участники прежнего процесса.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "array", "items": {"type": "object", "additionalProperties": true}, "title": "Response Document Workflows Api V1 Documents  Doc Id  Workflows Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`
- Code reference: [apps/api/app/workflows.py:312](../../apps/api/app/workflows.py#L312).

### API-055 — POST /api/v1/documents/{doc_id}/workflows

Purpose: Запустить процесс с закреплённой версией.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: owner; CAS; file/scan; required template/reviewer roles; owner исключён из plan.
- Path/query parameters и declarative validation: path `doc_id` required=True schema=`{"type": "string", "title": "Doc Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Start"}`
- Response schema / declared statuses: 201: application/json `{"type": "object", "additionalProperties": true, "title": "Response Start Api V1 Documents  Doc Id  Workflows Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID body idempotency_key обязателен; durable workflow_events.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 403 `'forbidden'`; 409 `'stale_document'`; 409 `'invalid_transition'`; 409 `'file_required'`; 422 `'invalid_workflow_template'`; 409 `'required_workflow'`; 409 `'required_stage_condition'`; 422 `'invalid_workflow_target'`; 422 `'empty_workflow'`; 422 `'unauthorized_reviewer'`; 422 `'invalid_workflow_target'`
- Code reference: [apps/api/app/workflows.py:328](../../apps/api/app/workflows.py#L328).

### API-056 — POST /api/v1/workflows/{instance_id}/decisions

Purpose: Принять решение или отменить процесс.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: текущий PENDING actor, selector и reviewer roles, card/file pinned version; cancel только owner.
- Path/query parameters и declarative validation: path `instance_id` required=True schema=`{"type": "string", "title": "Instance Id"}`
- Request body: application/json: `{"$ref": "#/components/schemas/Decision"}`
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Decide Api V1 Workflows  Instance Id  Decisions Post"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: UUID body idempotency_key обязателен; durable workflow_events.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 409 `'workflow_not_running'`; 409 `'document_in_trash'`; 409 `'workflow_scope_changed'`; 422 `'approval_comment_required'`; 404 `'not_found'`; 404 `'not_found'`; 403 if doc.owner_id == user.id else 404 `'not_assigned_approval'`; 403 `'unauthorized_reviewer'`; 409 `'workflow_scope_changed'`; 403 `'access_required'`
- Code reference: [apps/api/app/workflows.py:417](../../apps/api/app/workflows.py#L417).

### API-057 — GET /api/v1/approvals

Purpose: Получить свои текущие/завершённые задачи.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только свои задания; pending текущий этап; no title без допуска.
- Path/query parameters и declarative validation: query `view` required=False schema=`{"enum": ["pending", "completed", "rejected", "overdue", "cancelled"], "type": "string", "default": "pending", "title": "View"}`; query `page` required=False schema=`{"type": "integer", "minimum": 1, "default": 1, "title": "Page"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response My Approvals Api V1 Approvals Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: page offset; page_size если объявлен; см. parameter defaults.
- Прямые runtime errors: Прямых HTTPException в handler нет; возможны helper/global errors.
- Code reference: [apps/api/app/workflows.py:554](../../apps/api/app/workflows.py#L554).

### API-058 — GET /api/v1/approvals/{approval_id}/review

Purpose: Открыть своё текущее назначение либо access_required.

- Authentication: Cookie session + ACTIVE; mutation дополнительно Origin/CSRF.
- Authorization / Business rules: только своё текущее задание; без card/file возвращает access_required.
- Path/query parameters и declarative validation: path `approval_id` required=True schema=`{"type": "string", "title": "Approval Id"}`
- Request body: Отсутствует.
- Response schema / declared statuses: 200: application/json `{"type": "object", "additionalProperties": true, "title": "Response Review Task Api V1 Approvals  Approval Id  Review Get"}`; 422: application/json `{"$ref": "#/components/schemas/HTTPValidationError"}`
- Idempotency: begin/replay отсутствует; CAS/естественная повторяемость согласно handler.
- Pagination: Не объявлена; hard limits в handler/правилах выше.
- Прямые runtime errors: 404 `'not_found'`; 404 `'not_found'`
- Code reference: [apps/api/app/workflows.py:611](../../apps/api/app/workflows.py#L611).
