# Отчёт NEXORA — Iteration 1
Дата: 7 октября 2026, Asia/Qyzylorda. Реализована только Iteration 1. Commit и push не выполнялись.

1. **Реализация.** Рабочая core platform: локальная authentication, users/departments/RBAC, database-backed types, documents/metadata, secure uploads, immutable versions, lifecycle, comments, audit/activity, structured search, dashboard, RU/EN, Docker, миграция и seed.
2. **Архитектурные решения.** Modular monolith; PostgreSQL как источник истины; server-side opaque sessions; backend resource policy; private storage adapter; deterministic lifecycle; row locks и DB constraints; AI отдельно в будущем. Решения зафиксированы до реализации в docs/architecture.md.
3. **Repository structure.** apps/api и apps/web разделяют Python/Node зависимости, сборку и runtime; общие документы в docs. Это позволяет развивать backend и frontend без microservices/лишней инфраструктуры.
4. **Основные директории.** Полное дерево основной структуры:
```text
nexora/
  .env.example, .gitignore, .gitattributes, compose.yaml
  README.md, AGENTS.md
  apps/
    api/
      Dockerfile, .dockerignore, pyproject.toml, requirements.lock, alembic.ini
      app/
        __init__.py, config.py, db.py, models.py, schemas.py
        auth.py, policy.py, audit.py, body_limit.py
        documents.py, storage.py, catalog.py, main.py, seed.py
      migrations/
        env.py, script.py.mako, versions/0001_core.py
      tests/test_security.py, tests/test_api.py
    web/
      Dockerfile, .dockerignore, package.json, package-lock.json
      next.config.ts, tsconfig.json, next-env.d.ts, eslint.config.mjs
      src/
        lib/api.ts, types.ts, i18n.ts
        components/provider.tsx, shell.tsx, common.tsx
        app/
          layout.tsx, page.tsx, globals.css, not-found.tsx
          login/page.tsx
          (workspace)/
            layout.tsx, dashboard/page.tsx
            documents/page.tsx, new/page.tsx, [id]/page.tsx
            admin/users/page.tsx, audit/page.tsx
      tests/i18n.test.ts
  docs/
    architecture.md, product.md, security.md, iterations.md
    data-model.md, api.md, verification.md
```
5. **Backend modules.** config/db/models/schemas, session auth, centralized policy, document domain operations, private storage, audit writer, catalog/dashboard/admin, bounded request body, application entry point, seed.
6. **Frontend modules.** Typed API client и ошибки, localization provider/dictionaries, authenticated shell, tables/badges/errors; login/dashboard/list/create/detail/admin users/admin audit.
7. **Таблицы.** departments, users, auth_sessions, login_throttles, document_types, documents, document_versions, comments, audit_events; служебная alembic_version. Будущих workflow/AI tables нет.
8. **Constraints/indexes.** Foreign keys; unique email/codes/document number/storage key; unique(document_id,version_number); positive version/size; allowlisted role/status CHECK; composite current-version FK. Indexes для owner/type/department+status, children by document, session expiry/user и audit action/target/time. Triggers запрещают UPDATE/DELETE versions и audit.
9. **Миграция.** 0001_core — explicit frozen schema, sequence и immutable triggers, обратный downgrade. Upgrade, downgrade и повторный upgrade реально выполнены на nexora_test. Alembic check: No new upgrade operations detected.
10. **API.** Реальные endpoints перечислены полностью в docs/api.md: /health, /ready; auth login/me/logout; departments/document-types; users list/update; documents list/create/get/update/transitions; versions list/upload/download; comments list/add; activity; dashboard; audit. Base /api/v1. Никаких пустых future endpoints.
11. **Страницы.** /login, /dashboard, /documents, /documents/new, /documents/[id], /admin/users, /admin/audit. / перенаправляет на dashboard; localized not-found. Других декоративных страниц нет.
12. **Authentication.** Email/password проверяются backend, пользователь должен быть ACTIVE. Успех создаёт случайную сессию; неудача оставляет безопасное audit event. Ограничение попыток: 20 неудач за 15 минут на account/peer.
13. **Пароли.** Argon2id со случайной солью и параметрами PasswordHasher; plaintext в БД нет. DEMO_PASSWORD используется только development seed через environment. Dummy Argon hash снижает различие обработки unknown user.
14. **Session mechanism.** 48-byte random token в HttpOnly/SameSite=Lax cookie; SHA-256 token hash, user reference, CSRF token и expiry в DB. Срок 12 часов; Secure вне development. Logout удаляет session; текущая роль/status проверяются заново. Exact Origin для mutations, CSRF header для authenticated mutations. Session token не хранится localStorage.
15. **RBAC.** Централизованный PERMISSIONS. Все шесть ролей могут создавать свои документы и комментировать доступные. MANAGER получает department_read, ADMIN all_read/admin/audit. REVIEWER/APPROVER/LEGAL не получают глобальный доступ до workflow assignments.
16. **Resource authorization.** Owner/admin/manager-own-department policy применяется к lists/counts/details/versions/comments/activity/downloads. Child version дополнительно привязывается к document ID. Чужой resource даёт 404, запрещённое действие над видимым — 403.
17. **Document numbering.** PostgreSQL document_number_seq; DOC-<UTC year>-<at least six digits>. Sequence глобальная, не COUNT+1; gaps допустимы. Тест с 8 конкурентными create подтвердил уникальность.
18. **Lifecycle.** Отдельная action API с backend state/actor/business checks, row lock. Metadata PATCH не принимает status. SUBMITTED требует file. Решений approve/reject в этой итерации нет.
19. **Transitions.** DRAFT/REVISION_REQUIRED -> SUBMITTED; DRAFT/SUBMITTED/REVISION_REQUIRED -> CANCELLED; CANCELLED/APPROVED/REJECTED -> ARCHIVED. Reserved будущие статусы не устанавливаются клиентом. Неверный переход 409; неизвестный action 422.
20. **Upload.** Auth/resource/write policy; ограниченное чтение chunks, server key, content checks, SHA-256; version и audit в transaction. Ошибка commit удаляет новый файл.
21. **File security.** Extension и declared MIME allowlist, NFKC filename/control/separator normalization, PDF magic, UTF-8 TXT/NUL check, DOCX ZIP entries/count/size/encrypted/macro/entity checks. 20 MiB file cap и body cap до multipart spooling, private paths, exclusive file creation. Не является antivirus/full parser validation.
22. **Storage.** LocalStorage в private named volume /data/uploads. Storage protocol — extension point для S3/MinIO; сейчас только local adapter. Browser никогда не получает storage_key или public filesystem path.
23. **Versioning.** Каждая версия имеет отдельный UUID/key, sequence number, filename/MIME/size/hash/creator/time/change note. Старые файлы не перезаписываются; DB immutable triggers запрещают изменения/удаление version rows. Тест 4 конкурентных uploads получил версии 1..4.
24. **Current version.** documents.current_version_id обновляется после insert под document row lock; composite FK гарантирует принадлежность. До первого upload nullable.
25. **Download.** Проверяется действующая сессия, документ и принадлежность version. Streaming attachment, nosniff, Content-Length; успешное начало download фиксируется в audit. Старые версии доступны при разрешённом документе.
26. **Audit.** Actor/action/target/time/safe metadata/request UUID; бизнес-изменение и event в одной transaction. Login/failure/logout, user update, document changes/transitions, upload/version/download/comment. Activity — resource-scoped business view; global audit — ADMIN. Пароли/tokens/содержимое документов не записываются.
27. **Comments.** Реализованы document-level comments до 4000 символов, без threads/mentions/version-specific comments. Archived document нельзя комментировать.
28. **Search/filtering.** GET /documents: escaped ILIKE title/number; exact status/type/department, pagination 25 по умолчанию, максимум 100. Resource visibility встроена в запрос и total. Без AI/semantic search.
29. **Dashboard.** Реальные own/visible/in-progress/revision counters, последние 5 обновлённых документов, группы по статусам; API также возвращает by_type. Другой department USER видит нулевые counters для чужих документов.
30. **RU/EN.** Dictionaries + provider, русский server/default snapshot, localStorage только для языка, useSyncExternalStore для persisted preference, lang HTML обновляется. Status/event/error labels переводятся. Пользовательский контент не переводится автоматически.
31. **Seed.** 6 departments (IT/LEGAL/FINANCE/HR/OPERATIONS/MANAGEMENT), 9 types (CONTRACT/INVOICE/ORDER/MEMO/POLICY/ACT/APPLICATION/LETTER/OTHER), 7 синтетических users, 6 roles. Seed development-only и идемпотентный; не сбрасывает existing passwords.
32. **Credentials.** user/reviewer/approver/legal/manager/admin/other@nexora.local. Пароль из DEMO_PASSWORD; в .env.example — Nexora-Demo-2026!. LEGAL/other в LEGAL, остальные IT. Только development.
33. **Tests.** test_security.py: 10 parametrized unit cases; test_api.py: 6 PostgreSQL integration cases, включая concurrency. Frontend: 2 dictionary consistency/completeness tests.
34. **Security tests.** Anonymous/expired/revoked/blocked/disabled sessions; Origin/CSRF; role/department/owner policy; BOLA for document/files/comments/activity; arbitrary status/identity rejection; invalid lifecycle; type/file/size/traversal; cross-document version pointer; immutable audit/version DB operations; login throttling; concurrent numbering/version allocation.
35. **Команды проверок.** Реально выполнялись docker compose config --quiet/build/up/ps; python -m pytest -q (Docker run и exec, с NEXORA_TEST_DATABASE_URL); ruff check/format; mypy app; alembic upgrade/downgrade/check; npm install/ci, npm run test/lint/typecheck/build; npm audit и npm audit --omit=dev; git status/diff/check-ignore/diff --check; targeted source secret scan. Full test command для clean cache: docker compose exec -e NEXORA_TEST_DATABASE_URL=postgresql+psycopg://nexora:local-development-only@db:5432/nexora_test api python -m pytest -q -o cache_dir=/tmp/nexora-pytest.
36. **Backend tests.** Финально 16 passed, 0 failed, 0 skipped. Отдельный запуск без URL честно показал 10 passed/6 skipped. Осталось предупреждение Starlette о будущем переходе test client с httpx на httpx2; tests выполняются.
37. **Backend lint.** Финальный ruff check: All checks passed. Исправлены imports и форматирование; проверки не отключались.
38. **Backend typecheck.** Финальный mypy: Success, no issues found in 14 source files. Исправлены validator reuse и boolean inference.
39. **Frontend lint.** Финальный ESLint без ошибок/предупреждений. Исправлены hooks и navigation. Форматирование Prettier выполнено как временным инструментом, runtime dependency не добавлялась.
40. **Frontend typecheck.** tsc --noEmit и встроенная build typecheck прошли.
41. **Frontend build.** Next.js production build реально прошёл на Windows и в Docker. Финальный container использует standalone server и static assets, без полного development node_modules.
42. **Compose.** docker compose config --quiet прошёл. API/db healthy, web запущен; persistent named volumes. Все host ports привязаны к 127.0.0.1.
43. **Реальный запуск.** Да: Docker PostgreSQL, API и frontend. UI http://localhost:3300; API http://localhost:8800; PostgreSQL localhost:55432. Наличие Docker оказалось достаточным после запуска Desktop; чужие занятые порты не тронуты.
44. **Manual QA.** Браузер: login USER, dashboard, list, create и DOC-2026-000001, v1 upload/download, v2 upload с сохранением v1, details/metadata, comment/activity, submit -> SUBMITTED, RU->EN, reload persisted EN, logout, other user denied чужой card, USER denied admin page, ADMIN dashboard/users/audit. Live HTTP через web proxy: invalid archive 409, arbitrary PATCH status 422, original v1 content preserved, USER /users 403, revoked session 401, чужой document/file 404. Один синтетический smoke document с двумя версиями сохранён для ручного review; это не fake seed analytics.
45. **Невыполненные проверки.** Не выполнялись exhaustive cross-browser/mobile/manual accessibility, load/performance, antivirus, backup/restore или production deployment QA. Не заявляется полный security audit.
46. **Причины и исправленные препятствия.** Изначально Docker daemon был выключен, стандартные порты заняты, sandbox DNS/temp мешали install, первая venv не установила pip, bundled Python не подошёл psycopg binary. Решено запуском Docker, отдельными портами, project-local temp и разрешёнными downloads, нормальной Windows venv и Docker tests. Найденные package discovery/UTF-8/hooks/types/cache errors исправлены. Промежуточный downgrade старой тестовой схемы после изменения initial migration не прошёл; disposable schema пересоздана, финальный upgrade/downgrade/upgrade прошёл. Production/user data не удалялись.
47. **Limitations.** Development HTTP/example credentials; нет malware scanner/full PDF parser, recovery/orphan cleanup, retention/backups, password reset/registration, CRUD UI справочников, advanced workflow/notifications. Metadata editing last-write-wins. comments/activity/users capped. Production reverse proxy rate limiting требует доработки.
48. **Technical debt.** Cleanup expired sessions/throttle records, optimistic concurrency for metadata, page all auxiliary collections, separate migration/runtime DB roles, orphan reconciliation, production secrets/TLS, broader validation/QA. Full npm audit: 5 high records в development chain eslint-config-next -> fast-glob -> micromatch -> braces. По advisory GHSA-vfj7-8cjw-p6xm patched version отсутствует; npm view braces подтвердил 3.0.3. npm audit --omit=dev: 0 vulnerabilities. Dependency warnings не скрыты; lint получает только trusted repository patterns, dev tools исключены из final web runtime. Источник: [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
49. **Iteration 2.** WorkflowDefinition/Version/Instance, participant assignments, sequential steps, reason-required approve/reject/revision, resource checks, audit, deadlines и internal notifications. Сейчас эти таблицы/endpoints не созданы.
50. **Не реализован roadmap.** AI/LLM/providers/parsing/jobs/Redis/embeddings/pgvector/RAG/chat/risk/comparison/OCR; advanced/parallel/conditional workflows/escalation/delegation; email/Telegram/SSO/LDAP/ЭЦП/НУЦ/1С/SAP/Kubernetes/mobile/MCP. Ни fake integrations, ни AI dependencies.
51. **Backend entry points.** apps/api/app/main.py — app; documents.py — domain API; auth.py/policy.py — session/access; models.py/schemas.py — data; storage.py — files; seed.py — development seed; migrations/env.py — Alembic.
52. **Frontend entry points.** src/app/layout.tsx и (workspace)/layout.tsx; components/provider.tsx/shell.tsx; lib/api.ts/i18n.ts; route page.tsx files. next.config.ts содержит same-origin rewrite и headers; Docker build задаёт внутренний http://api:8000 до build.
53. **Windows запуск.** Для текущего подготовленного workspace: cd C:\Users\zamirzhan.janbakiyev\Projects\nexora; docker compose up --build. Затем http://localhost:3300. Для чистого clone сначала Copy-Item .env.example .env, при занятых портах поправить WEB_PORT/API_PORT/POSTGRES_PORT и соответствующий WEB_ORIGIN. Не перезаписывать уже подготовленный .env. Полные инструкции в README.
54. **Действия пользователя.** Сейчас приложение уже запущено. Для следующего запуска нужен работающий Docker Desktop/Linux containers; local Python/Node необязательны. Никаких AI keys/cloud accounts не нужно. Credentials — development-only.
55. **git status --short.** Новый Git repository без initial commit: ?? .env.example; ?? .gitattributes; ?? .gitignore; ?? AGENTS.md; ?? README.md; ?? apps/; ?? compose.yaml; ?? docs/. Ничего не staged/committed/pushed.
56. **Git diff summary.** git diff --stat и --check пусты, потому что все файлы untracked и нет baseline commit. Фактические изменения: новая monorepo core implementation, Compose, 1 migration, 2 backend test files и localization test, документация. Это не утверждение об отсутствии изменений.
57. **Secrets/generated files.** Targeted source scan не нашёл private keys/real API tokens. .env, .tmp, venvs, node_modules, .next, caches, tsbuildinfo, egg-info, uploads/DB files исключены .gitignore; git check-ignore реально подтвердил основные пути. Example passwords только synthetic development. Uploads и DB — private Docker volumes. Screenshot .tmp/nexora-dashboard.png и QA files ignored; скачанный synthetic qa-v1.txt вне repository.
58. **Отклонения.** Git directory отсутствовал — выполнен только git init main. Локальные порты 3300/8800/55432 вместо занятых 3000/8000/5432. Search endpoint реализован через GET /documents, отдельного /search нет (спецификация допускает направление API). ADMIN только users access editing и audit; справочники seed-backed без управления UI. Comments реализованы. Advanced future функции намеренно отсутствуют; новые проверки сверх минимума: DB immutability, body cap, rate limit, concurrency, dictionary tests. Не пропущены required Iteration 1 функции ради будущего roadmap.
59. **Рекомендуемый commit message.** feat: implement NEXORA iteration 1 core document platform. Commit не создавался.
60. **Ручная проверка после работы.** Войти user@nexora.local, увидеть smoke document и обе версии, скачать v1/v2, проверить RU/EN, создать собственный черновик и пройти upload/submit/cancel/archive. Войти other для denied доступа, manager для department visibility, admin для users/audit. Проверить UX на своём экране и длинных названиях/реальных разрешённых форматах. Не использовать реальные sensitive documents до дальнейшего hardening.

Iteration 2 не начата. Приложение оставлено запущенным для review.


## Enterprise increment — DMS (2026-10-07)
VERIFIED: baseline regression 16/16 before changes, baseline commit 059f7de; no remote configured. Secrets pattern scan of source/docs found no private keys or token patterns. .env, uploads, dependencies and build outputs excluded.
VERIFIED: 20 backend cases (PostgreSQL): prior 16 plus DMS lifecycle/authorization, simultaneous folder move cycle prevention, custom type field validation/admin enforcement, structured metadata reference/date validation. No skipped tests in the configured run. Starlette emits one TestClient/httpx deprecation warning.
VERIFIED: 4 frontend tests: matching RU/EN dictionaries, status/events, static translation calls, AST check for prose JSX outside localization (brand name exempt).
VERIFIED: backend Ruff and mypy; frontend lint/typecheck; Windows and Docker production builds for DMS/custom fields, then Docker build including structured metadata. Windows build needs elevated filesystem access because SWC canonicalization is blocked by the sandbox; retry succeeds.
VERIFIED: migrations 0002_dms and 0003_metadata upgrade existing app DB and preserve original document DOC-2026-000001; fresh database nexora_install_check installs; Alembic check reports no drift. Downgrade to 0001 and re-upgrade tested on disposable DB only. Downgrading discards newly introduced metadata; never use it as a production rollback without backup.
VERIFIED browser smoke: admin login, type QA_POLICY with required nonnegative numeric budget, private folder, document DOC-2026-000002 with budget 250000 and structured fields, favorite, move into folder and visible filtered result, trash disappears from active list, trash details have no edit/upload/comment actions, restore returns actions and audit, EN switch and preference after reload. One browser tab stalled after native confirmation; a fresh tab verified successful trash and restore. Screenshot .tmp/nexora-dms-qa.png (local ignored proof).
PARTIALLY VERIFIED: DMS phase. Private folders and five document views implemented; company-wide folders, resource ACL, Shared with Me, true per-user Recent, permanent purge and retention policies remain unimplemented. User references use IDs in forms; no access-aware directory selector yet. Full accessibility/responsive matrix and persisted browser E2E are pending.
NOT VERIFIED / not implemented: workflow, tasks, notifications, granular RBAC/ACL, MFA/OIDC, antivirus, backup restore, AI, advanced fulltext/exports/analytics, SMTP/webhooks/tokens, tenants, onboarding/settings and large benchmark. Existing Iteration 1 dependency findings remain pending a fresh enterprise audit. This increment is not a commercial release claim.
