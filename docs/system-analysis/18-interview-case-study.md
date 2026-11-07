# Interview Case Study

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Формулировки ниже можно адаптировать к своему фактическому вкладу. Не утверждайте, что лично выполняли все этапы разработки/аналитики, если это не подтверждается.

## 1. Бизнес-проблема

Восстановленная потребность: неверные версии, потеря решений и лишний доступ. Доказательств реального заказчика нет.

## 2. Цель системы

Управляемый документный lifecycle и проверяемая история с минимальными правами.

## 3. Заинтересованные стороны

Owner, назначенный участник, MANAGER, ADMIN и department-scoped CUSTODIAN/SECURITY. Не добавлять AUDITOR в AS-IS.

## 4. Границы решения

Модульный монолит; документы/версии/маршруты/ACL. Без юридической ЭП, CRM и внешнего workflow engine.

## 5. Основной бизнес-процесс

DRAFT → upload → start IN_APPROVAL → решения текущего этапа → APPROVED. revision открывает новую итерацию, reject терминален.

## 6. Функциональные требования

18 восстановленных FR; пример FR-006 закрепляет версию, исключает owner, проверяет required route и ACTIVE targets.

## 7. Архитектура

Next same-origin proxy → FastAPI → PostgreSQL; API → private files + ClamAV. ACL и lifecycle на backend.

## 8. API

58 операций REST v1; raw OpenAPI плюс runtime supplement. Cookie/CSRF и ключи повторов частично отсутствуют в generated schema.

## 9. Модель данных

24 таблицы, 195 полей; documents/current version composite FK, immutable versions/events, scoped grants/receipts.

## 10. Управление доступами

ADMIN не читает всё; MANAGER approved PUBLIC/INTERNAL отдела; назначенный участник только current pinned scope; restricted двойное одобрение.

## 11. Альтернативные сценарии

Старая revision409; scanner503; future participant404; повтор UUID replay; revision позволяет новый процесс, reject — не прямой resubmit.

## 12. Риски

Type-only mandatory route, бесконечные keys, локальная storage topology, непроверенный deployment, incomplete OpenAPI.

## 13. Критерии приёмки

Given current actor и закреплённая версия; When он решает; Then один receipt/audit, переход только после всех, future reader denied.

## 14. Технические компромиссы

Синхронное сканирование проще и fail-closed, но задерживает upload; PostgreSQL транзакции не охватывают filesystem, нужны reconcile/backup.

## 15. Улучшения

Классификационные маршруты, tombstones, typed contract, outbox, SSO/MFA, метрики и нагрузочное тестирование.

## Презентация примерно на 2 минуты

NEXORA — мой портфолио-кейс анализа корпоративного документооборота. Документация восстановлена по существующему коду; я не представляю её как коммерческий заказ или требования реального клиента. Я начал с границ: Next.js отвечает за интерфейс, FastAPI — за решения и права, PostgreSQL — за транзакции, файлы хранятся приватно. Затем связал бизнес-цели с требованиями, API, сущностями и реальными тестами. Ключевой сценарий — согласование закреплённой версии. Будущий этап ещё не получает документ; после решения остаётся квитанция, а новая версия не наследует прежние допуски. Для RESTRICTED нужны два независимых подтверждения, привязанные к конкретному scope и сроку. На этом примере можно показать работу с негативными сценариями: повтор запроса, конфликт редактирования, смена роли и отказ сканера. Я отдельно отметил границы: обязательный маршрут сейчас задаётся по типу, retention ключей не решён, OpenAPI не полностью описывает runtime security. Результат — связанный комплект BR/FR/NFR, BPMN/UML, модель данных и RTM, который помогает обсуждать систему по доказательствам, а не по красивому описанию. Production готовность требует отдельного внедрения и восстановления, их этот документационный этап не подтверждает.

## Техническое объяснение примерно на 5 минут

Первые 60 секунд: покажите контекст и границу доверия. Browser общается с same-origin API через Next rewrite; cookie HttpOnly не задаёт роль. current_user читает сессию и ACTIVE user, mutation проверяет CSRF и Origin. Это отличает UI capability от реальной серверной защиты.

Следующая минута: разберите создание и файл. POST documents назначает owner/dept и sequence number. Multipart upload отдельный: bounded stream, формат, quarantine, ClamAV, promote; document lock защищает allocation номера версии. DB фиксирует ссылку и аудит, но filesystem не входит в SQL transaction. После потерянного commit acknowledgement blob сохраняется, чтобы не удалить подтверждённые данные; позже operator сверяет orphan с БД.

Третья минута: start фиксирует current version и immutable template, snapshot карточки и план ACTIVE людей. Owner исключён из согласующих. Этапы последовательны, участники внутри этапа работают параллельно с единогласием. Проверяется exact required template и reviewer roles, но requirement key пока только type, что ограничивает классификационную политику.

Четвёртая минута: ACL строится SQL predicates по действующему основанию. Owner сохраняет независимый доступ. MANAGER имеет только approved PUBLIC/INTERNAL current version отдела; draft opt-in handoff даёт персональные captured grants. ADMIN управляет системой без blanket content. Current PENDING участник видит pinned version, будущий нет. RESTRICTED дополнительно требует scoped card/file grant, двумя разными offices. После решения receipt не позволяет скачивание; frozen snapshot имеет отдельный срок/правила.

Пятая минута: объясните отказ и доказательства. PATCH CAS предотвращает lost update; actor UUID и fingerprint предотвращают двойную операцию, но keys ещё без retention. Ошибки имеют safe code/request_id, скрытые документы404. Покажите RTM с существующими test functions и Missing Test, raw OpenAPI с дополнением вместо выдуманных схем. Закончите рисками и критериями дальнейшего rollout: verified restore DB+files, реальные независимые offices, runtime без SUPERUSER и совместный web/API. Не обещайте SLA, которого не измеряли.

## 15 вопросов и ответов

### 1. Почему монолит?

Код организован модулями в одном API и общей БД. Это упрощает транзакции workflow/ACL; микросервисы не подтверждены и не нужны для красивого кейса.

### 2. Как нашли требования?

Reconstructed requirements из routers, schemas, policy и тестов; подтверждение реального заказчика не заявляется.

### 3. Почему не доверять кнопкам?

Frontend capabilities помогают UX, backend заново проверяет session/ACTIVE/ACL для каждого request.

### 4. Как избежать BOLA?

Проверять document и конкретную version, SQL visibility на lists/search, 404 скрытого ресурса; сравнение проверяет обе версии.

### 5. Что умеет ADMIN?

Users/types/templates/session admin; не blanket content. Audit document events ограничены owner.

### 6. Как согласуется версия?

WorkflowInstance закрепляет document_version_id и snapshot; decision проверяет нынешний document version/status и план.

### 7. Что с параллельным этапом?

Каждый PENDING actor принимает своё решение; этап меняется после отсутствия других PENDING участников.

### 8. Reject и revision одинаковы?

Нет. REJECTED терминален без direct edit/resubmit; REVISION_REQUIRED разрешает новый процесс с сохранением прежнего.

### 9. Как работает RESTRICTED?

Grant scope/hash, request window24h, доступ≤8h; два distinct CUSTODIAN/SECURITY actors, без requester/recipient self-approval; проверки продолжаются при каждом чтении.

### 10. Что остаётся после решения?

Собственная квитанция can_download=false; frozen snapshot только по ограниченным условиям или отдельному grant, не live карточка.

### 11. Как обработан retry?

Actor+UUID lock и fingerprint; same request replay, different payload409. Старые ключи не удаляются, retention gap признан.

### 12. Как решить lost update?

Expected revision/timestamp плюс locks; stale409, omitted PATCH fields сохраняются.

### 13. DB и файл атомарны?

Нет. Не удаляем потенциально committed blob после lost acknowledgement; quarantine и DB-confirmed sweep с grace, backup DB+files.

### 14. Что неполно в OpenAPI?

Cookie/header security, custom error envelope, generic dict responses; raw сохранён и gap документирован.

### 15. Готово ли для реальной компании?

По этой документации нельзя доказать readiness. Нужны rollout/restore verification, назначение полномочий, load/UX checks и устранение P0; рабочая среда не исследована.

Для демонстрации используйте [API](10-api-specification.md), [ACL](13-security-and-access.md), [RTM](16-requirements-traceability.md) и [gaps](17-gap-analysis.md) как доказательства. Для резюме допустимо: «Подготовил аналитическую документацию портфолио-системы NEXORA: восстановленные требования, BPMN/UML, контракты REST, ERD, ACL и трассировку на исходный код и тесты». Не добавляйте выручку, количество реальных компаний и production SLA.
