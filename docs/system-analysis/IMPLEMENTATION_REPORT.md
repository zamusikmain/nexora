# Отчёт о создании аналитической документации NEXORA

Срез: 11.10.2026, ветка `feature/nexora-workflow-hardening`, исходный HEAD `34151f79ceac89348fed0b93fa807ccdb9c452c3`. Документация описывает исходный код ветки. Применение этого кода и миграций в рабочей среде не проверялось.

## 1. Изученные компоненты

Изучены FastAPI routers и middleware, Pydantic schemas, SQLAlchemy metadata, цепочка Alembic 0001…0008 и защитные downgrade, session authentication, SQL ACL и grants, lifecycle документов и согласований, custom fields, storage/scanning, аудит, operator cleanup, backup/restore и DB-role инструменты. Frontend: Next pages/components, API wrapper, RU/EN dictionaries, capability/task-driven загрузка, tests/config/build. Проверены Dockerfiles и четыре Compose-конфигурации. Рабочие документы и секреты не использовались как источники примеров.

## 2. Подтверждённые функции

В коде есть локальный вход, сессии и отзыв, CSRF/Origin/ACTIVE checks, регистрация карточек и серверная нумерация, метаданные/custom fields, приватные PDF/DOCX/TXT, immutable версии, checksum и production scan attestation, поиск/dashboard с ACL, личные папки/избранное/корзина/восстановление/TXT diff, комментарии и аудит, versioned workflow templates, этапы и единогласие, решения/квитанции, scoped временные допуски и двойное RESTRICTED endorsement. PostgreSQL runtime/migrations/backup разделяются opt-in конфигурацией и operator provisioning; это не доказательство текущих полномочий рабочего API.

## 3. Частичная реализация и неизвестное

Mandatory workflow requirement зависит от type, без отдельного классификационного ключа. Дедлайны дают overdue view без автоматических уведомлений/эскалации. Повторы защищены долговечными ключами, но retention не реализован. Raw OpenAPI не полностью выражает security и runtime responses. UI unit tests не подтверждают весь browser/accessibility UAT. Производительность, SLA, live schema и готовность предприятия Unknown. ИИ, SSO/MFA, broker/outbox и отдельная роль AUDITOR отсутствуют в AS-IS; их развитие — предложения.

## 4–5. Требования и структура

Созданы 18 тематических разделов, навигация, данный отчёт, приложение с полным Data Dictionary, исходники диаграмм, OpenAPI и [машинная сводка проверок](verification-results.json). Всего 37 файлов в `docs/system-analysis/`.

| Артефакт | Количество | Основание |
|---|---:|---|
| BR | 8 | Reconstructed по реализации |
| FR | 18 | Actors/flows/errors/postconditions/AC и code references |
| NFR | 10 | Подтверждённые механизмы отдельно от предложений и Unknown |
| User Stories | 18 | Связь с BR/FR и критериями Given/When/Then |
| Use Cases | 8 | Связь с FR и фактическими входными операциями |
| Acceptance criteria groups | 21 | 18 основных + 3 граничных |

Это восстановленная аналитика портфолио-проекта. Официальное согласование реальным заказчиком, экономический эффект и личное выполнение всех этапов разработки не заявлены.

## 6. Диаграммы

4 BPMN 2.0 XML с BPMN DI и lanes: регистрация, согласование, reject/revision/resubmit, управление доступом. 6 UML-источников: Use Case и Component в PlantUML, четыре sequence в Mermaid. Дополнительно ERD и архитектурный flowchart. Итого 12 файлов диаграмм; flowchart не называется полноценной BPMN.

BPMN аналитические, `isExecutable=false`. Каждый XML открыт локальным bpmn-js Modeler 18.31.0 в браузере: import без warnings, SVG экспорт сформирован для всех четырёх. Редактор использовал только временную папку с копиями диаграмм. Выполнена визуальная проверка страницы. Mermaid проверен parser; PlantUML проверен структурно (границы, объявленные actors/components и ссылки), но не отрендерен: Java/PlantUML runtime не обнаружен. Это оставшееся ограничение качества, не полноценное подтверждение renderer compatibility.

## 7. API

58 method/path операций на 49 paths. [Raw OpenAPI 3.1.0](openapi/fastapi.openapi.json) экспортирован из `app.openapi()` без соединения с PostgreSQL. Полный per-endpoint каталог содержит параметры, request/response schemas, authentication/authorization, pagination, idempotency, runtime errors и ссылки на handlers. [contract-notes.json](openapi/contract-notes.json) отдельно описывает фактическую manual security/повторы. TO-BE endpoints не добавлены. Синтетические JSON examples не содержат реальных данных.

## 8. Модель данных

24 ORM-таблицы, 195 полей; все поля перечислены с типом, nullable, default и его источником Python/server, назначением, PK/FK/UNIQUE. Все metadata constraints и indexes описаны. ERD извлечён из тех же metadata: FK connectivity и cardinality по nullable/PK/UNIQUE, composite relationships сохранены. Служебная alembic_version и sequence описаны отдельно. Триггеры миграций указаны сверх ORM. Прямого сравнения с рабочим PostgreSQL не было, поэтому live drift остаётся Unknown.

## 9. Подтверждённые интеграции

5 границ: Browser/Next→API, API→PostgreSQL, API→private filesystem, API→ClamAV INSTREAM, operator→Docker/PG/backup archives. Для каждой указаны protocol/auth/format, timeout/retry/idempotency/errors/observability. Прикладной broker, CRM и асинхронный worker не подтверждены и не изображены как существующие.

## 10. Пробелы

[Gap Analysis](17-gap-analysis.md) содержит 13 записей с доказательством/статусом, impact, приоритетом, решением, сложностью и зависимостями. Главные: классификационные mandatory routes, lifecycle ключей повторов, incomplete OpenAPI, неподтверждённый rollout/DB privileges, отсутствие notifications/escalation и enterprise identity, local storage topology, observability, отсутствие независимой роли аудитора, пределы коллекций, непроверенная accessibility, DB/files consistency и Windows fixture backup.

## 11. Выполненные проверки

| Проверка | Результат |
|---|---|
| Markdown file links и source line bounds | 527 локальных ссылок и границы source lines проверены; итоговые машинные результаты в verification-results.json |
| Mermaid | 6 файлов + обзор в root README проходят parser |
| BPMN | bpmn-moddle: 4 XML, 0 warnings; bpmn-js browser editor import/SVG: 4/4 |
| OpenAPI | swagger-parser 13.1.0: OpenAPI 3.1 schema и internal refs валидны; external resolving отключён |
| API / raw schema / supplement | Совпадают все 58 method/path; фиктивных endpoints не найдено |
| Data Dictionary / ERD | Все 24 таблицы/195 полей из metadata; FK и constraints прослеживаемы |
| ACL matrix | Сверена с auth/policy/access/documents/catalog/workflows; ADMIN-all и blanket MANAGER draft не утверждаются |
| RTM | 18 FR связаны с BR/US, точным API, сущностью, существующими test functions; Missing Test отмечен |
| Новые артефакты: секреты/данные | Credential signatures, private-key/DB/dump/file extensions и личные email не найдены; примеры synthetic |
| Backend / ops unit suite | 162 уникальных cases прошли, 363 integration cases skipped, 1 Windows fixture failed; детали ниже |
| Ruff / mypy | Ruff app passed; mypy — 22 source files без ошибок |
| Frontend | 5 tests passed; TypeScript и ESLint passed; production build passed (Next.js 16.4.0) |
| Изменение исходного кода | Tracked diff — README; новые файлы только docs/system-analysis; application source не изменён |

Backend: основной запуск дал 161 passed / 363 skipped / 1 failed / 1 deselected. Отдельно выбранный deselected test_missing_backup_credential_fails_closed прошёл через установленный Git sh, получаем 162 уникальных passed. Единственный failed — test_backup_script_archives_real_private_keys: fixture вставляет Windows `C:\Users` в генерируемый script, получая unicodeescape SyntaxError. Test body не достиг архивации. Код не исправлялся; GAP-013 описывает границу. Прочие archive integrity/unsafe path проверки прошли.

Первичные попытки: pytest collection без ops в PYTHONPATH, temp/socket ограничения sandbox и SWC Windows path access помешали запуску. Они устранены конфигурацией окружения/временной папки и повтором вне sandbox; не изменением кода. Итоговая ошибка fixture воспроизводится вне sandbox. Наличие предупреждения Starlette/httpx deprecated отдельно от ошибок тестов.

## 12. Невыполненные проверки

PostgreSQL integration tests, privilege checks against running DB, migrations upgrade/downgrade, live Alembic drift и полноценный restore DB+files в этом этапе не запускались. Fixture integration выполняет upgrade/TRUNCATE, поэтому NEXORA_TEST_DATABASE_URL был удалён из окружения. Docker Engine при read-only проверке недоступен. Рабочая БД не опрашивалась и не изменялась; рабочие uploads/контейнеры не трогались. Исторические результаты других заданий не выдаются за свежие.

Не выполнен renderer check PlantUML и полный browser UAT приложения RU/EN; browser-проверка выше относится только к BPMN editor. Secret scan — локальные signatures и обзор новых файлов, не независимая сертификация или полная история Git.

## 13. README

Добавлен System Analysis & Architecture с навигацией, BPMN/UML/API/ERD/RTM/кейcом и Mermaid overview. Исправлены устаревшие claims об отсутствии granular ACL, optional revision PATCH и сохранении доступа всем workflow participants. Existing dev/start/test/deployment sections сохранены. AGENTS.md остаётся историческим источником Iteration 1; документация явно объясняет его несовпадение с текущей ACL.

## 14. Ограничения и действия дальше

Документы пригодны для анализа и обсуждения системы по коду. Для внедрения нужны отдельное разрешение, verified restore на изолированной копии, runtime privilege verification, независимые CUSTODIAN/SECURITY со сроками, approved mandatory-route matrix и совместное обновление web/API. Численные NFR требуют согласования и измерения. При последующих изменениях API/ORM/ACL необходимо переснять OpenAPI, dictionary и RTM.

Никаких commit, push, merge, deployment, применения миграций, удаления/пересоздания БД или переключения рабочих DB-ролей не выполнялось. Предшествующие untracked `docs/predeployment-audit.md` и `docs/predeployment-demo.json` сохранены.

## 15. Для резюме и собеседования

Можно использовать [кейс с 2- и 5-минутными объяснениями и 15 Q&A](18-interview-case-study.md), BPMN/UML, API, ERD и RTM. Корректная формулировка: «Подготовил аналитическую документацию портфолио-проекта NEXORA: восстановил требования по реализации, описал REST API и данные, смоделировал процессы/ACL и связал требования с тестами». Не заявлять коммерческий заказ, согласование реального клиента, production SLA и непроверенный собственный вклад.
