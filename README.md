# NEXORA
Корпоративное управление документами. Portfolio project, Iteration 1.

## IMPLEMENTED
FastAPI, SQLAlchemy, PostgreSQL, Alembic; Next.js, React, TypeScript. Локальный вход с Argon2id, серверные сессии, CSRF, login throttling; пользователи, 6 ролей, статусы и подразделения; database-backed RU/EN типы документов. Регистрация, metadata, поиск/фильтры, приватные immutable версии PDF/DOCX/TXT и скачивание; submit/cancel/archive; комментарии, activity, admin audit и редактирование доступа пользователей; dashboard из реальных данных; RU/EN. Docker Compose, миграция, development seed и тесты.

## Первый запуск на Windows
Требуется Docker Desktop с Linux containers. Python/Node на хосте не обязательны.
```powershell
cd C:\Users\zamirzhan.janbakiyev\Projects\nexora
# Копировать только если .env ещё не существует:
Copy-Item .env.example .env
docker compose up --build
```
По умолчанию UI http://localhost:3000, API http://localhost:8000/api/docs. Если порт занят, измените WEB_PORT, API_PORT, POSTGRES_PORT в .env; WEB_ORIGIN должен совпадать с адресом браузера.
**Подготовленный локальный .env уже использует UI 3300, API 8800, PostgreSQL 55432 из-за занятых стандартных портов. Не перезаписывайте его без необходимости.**
Миграция/seed запускаются автоматически. PostgreSQL/private uploads сохраняются в named volumes. Остановка: `docker compose stop`; не удаляйте volumes, если нужны данные.

### Development credentials
user@nexora.local, reviewer@nexora.local, approver@nexora.local, legal@nexora.local, manager@nexora.local, admin@nexora.local, other@nexora.local. Пароль задаёт DEMO_PASSWORD в .env; в примере `Nexora-Demo-2026!`. Только синтетические local accounts. Seed требует APP_ENV=development и SEED_DEMO=true, повторный запуск не сбрасывает пароли и пользователей.
LEGAL/other относятся к LEGAL, остальные к IT. Для проверки BOLA создайте документ под USER и откройте под other.

## Проверки
```powershell
docker compose config --quiet
docker compose exec api python -m ruff check .
docker compose exec api python -m mypy app
docker compose exec api alembic check
# Создать одноразовую тестовую БД один раз:
docker compose exec db psql -U nexora -d nexora -c "CREATE DATABASE nexora_test"
# При другом пароле БД измените URL локально:
docker compose exec -e NEXORA_TEST_DATABASE_URL=postgresql+psycopg://nexora:local-development-only@db:5432/nexora_test api python -m pytest -q -o cache_dir=/tmp/nexora-pytest
cd apps/web
npm ci
npm run test
npm run lint
npm run typecheck
npm run build
```
Integration tests принимают только БД nexora_test и очищают только её таблицы. Без NEXORA_TEST_DATABASE_URL они явно skipped; unit tests работают. Не используйте рабочую БД.
Локальный backend: `python -m venv .venv`, `.venv\Scripts\python -m pip install -r requirements.lock`, `.venv\Scripts\python -m pip install --no-deps -e .`; DATABASE_URL и STORAGE_ROOT задаются окружением. Для frontend вне Docker API_INTERNAL_URL задайте **до npm run build**: rewrite фиксируется при сборке.

## PLANNED
Iteration 2: versioned workflows, assignments, sequential approve/reject/revision with reasons, deadlines и internal notifications. Затем optional AI/providers/parsing/pgvector/permission-aware RAG. Эти функции не реализованы.

## LIMITATIONS
Не production certification. Development HTTP и примерные credentials требуют замены для эксплуатации. Нет регистрации/password reset, UI создания пользователей и управления справочниками. REVIEWER/APPROVER/LEGAL имеют owner-level access до появления workflow assignments. Approve/reject/revision actions отсутствуют, прямое изменение status запрещено.
Нет antivirus, полноценной проверки PDF/DOCX или content disarm. Crash между file write и DB commit может оставить orphan; reconciliation/backups/retention отсутствуют. Metadata editing без optimistic concurrency token, последняя запись выигрывает. Comments ограничены 500, activity 200, admin users 500; documents/audit paginated. Нет фоновой очистки sessions/throttle rows. Reverse proxy объединяет peer rate limit; нужен production rate-limit design.
Нет уведомлений, realtime, advanced workflow, AI, MCP или внешних интеграций. Полные результаты и предупреждения dependency audit: docs/verification.md.

## Документация
[Architecture](docs/architecture.md), [Product](docs/product.md), [Security](docs/security.md), [Iterations](docs/iterations.md), [Data model](docs/data-model.md), [API](docs/api.md), [Verification](docs/verification.md), [Agent guide](AGENTS.md).
