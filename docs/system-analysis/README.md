# NEXORA — System Analysis & Architecture

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

## Как читать

Начните с продукта и границ, затем требований и процессов. Для технического обсуждения используйте API, модель данных и ACL; для собеседования — кейс. AS-IS описывает код; TO-BE — предложения, требующие выбора и проверки. Unknown означает отсутствие доказательств, а не отсутствие функции.

- [Product Overview](01-product-overview.md)
- [Stakeholders & Scope](02-stakeholders-and-scope.md)
- [Business Requirements](03-business-requirements.md)
- [Functional Requirements](04-functional-requirements.md)
- [Non-Functional Requirements](05-non-functional-requirements.md)
- [Business Processes](06-business-processes.md)
- [User Stories](07-user-stories.md)
- [Use Cases](08-use-cases.md)
- [System Architecture](09-system-architecture.md)
- [API Specification](10-api-specification.md)
- [Data Model](11-data-model.md)
- [Integrations](12-integrations.md)
- [Security & Access](13-security-and-access.md)
- [Error Handling](14-error-handling.md)
- [Acceptance Criteria](15-acceptance-criteria.md)
- [Requirements Traceability](16-requirements-traceability.md)
- [Gap Analysis](17-gap-analysis.md)
- [Interview Case Study](18-interview-case-study.md)
- [Результат и проверки](IMPLEMENTATION_REPORT.md)
- [Диаграммы](diagrams/README.md)
- [Фактический OpenAPI](openapi/fastapi.openapi.json)
- [Дополнения контракта из кода](openapi/contract-notes.json)

## Карта AS-IS

| Компонент | Ответственность | Статус | Доказательство |
|---|---|---|---|
| Next.js / React / TypeScript | UI, RU/EN, формы, повтор операций | Implemented | [apps/web/src/lib/api.ts](../../apps/web/src/lib/api.ts) |
| FastAPI / Pydantic | HTTP, валидация, сессия, ACL | Implemented | [apps/api/app/main.py](../../apps/api/app/main.py) |
| SQLAlchemy / PostgreSQL / Alembic | Транзакции, 24 таблицы, 8 миграций | Implemented | [apps/api/app/models.py](../../apps/api/app/models.py) |
| LocalStorage / ClamAV | Приватные immutable-файлы, синхронная проверка | Implemented; production-настройка Unknown | [apps/api/app/storage.py](../../apps/api/app/storage.py) |
| Workflow | Этапы, параллельные решения, квитанции | Implemented; эскалации Planned | [apps/api/app/workflows.py](../../apps/api/app/workflows.py) |
| Обязательные маршруты | По типу, без классификационного ключа | Partially implemented | [apps/api/app/models.py](../../apps/api/app/models.py) |
| Разделение DB-ролей | Opt-in конфигурация и операторские проверки | Implemented в поставке; применение Unknown | [compose.roles.yaml](../../compose.roles.yaml) |
| ИИ, SSO, брокер, внешняя CRM | Отсутствуют в коде | Planned | [Границы](02-stakeholders-and-scope.md) |

AGENTS.md содержит исторические инварианты Iteration 1: blanket ADMIN/MANAGER access не описывает текущую ACL Revision 2. Приоритет в этой документации имеют серверные проверки текущей ветки.
