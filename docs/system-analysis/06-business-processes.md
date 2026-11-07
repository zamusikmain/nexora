# Business Processes

Срез исходного кода: `feature/nexora-workflow-hardening`, `34151f79ceac89348fed0b93fa807ccdb9c452c3`, 11.10.2026. Implemented означает наличие реализации в этой ветке, а не подтверждение её развёртывания. Рабочая БД не опрашивалась. Требования восстановлены из кода (reconstructed requirements); это портфолио-проект, не согласованный BRD реального заказчика.

Диаграммы BPMN 2.0 — аналитические модели, isExecutable=false. Они не исполняются NEXORA. Tasks объединяют действия пользователя и транзакции API; ошибки показывают бизнес-ветку, а не автоматический retry. [Источники и проверка](diagrams/README.md).

## BP-01: создание и регистрация

Участники: инициатор, API. Автор вводит поля; API проверяет session/CSRF, тип и метаданные, выдаёт sequence number, создаёт DRAFT и аудит. Файл загружается отдельной операцией: карточка может существовать без версии. Ошибка validation не регистрирует документ; повтор одного UUID не регистрирует второй. ClamAV относится к отдельному upload шагу, не к POST карточки. [BPMN](diagrams/create-document.bpmn), [sequence](diagrams/create-document.mmd). FR-001/003.

## BP-02: согласование

Участники: owner, API, текущие согласующие. Start принимает закреплённый template и expected_revision, проверяет файл, план и requirement. Первый этап PENDING; будущие WAITING не видят документ. Каждый текущий участник имеет card/file scope. approve открывает следующий этап только после всех решений текущего. Последний этап делает документ APPROVED. reject/revision завершают процесс, cancel доступен owner. Отзыв review grants и аудит в той же транзакции. [BPMN](diagrams/approval.bpmn), [sequence](diagrams/start-workflow.mmd), [decision](diagrams/decision.mmd). FR-006…009.

## BP-03: отклонение и повторная отправка

Участники: согласующий, owner, API. Нельзя смешивать reject и revision. reject → REJECTED: исправление и прямой resubmit не реализованы; возможен archive. revision → REVISION_REQUIRED: owner редактирует, создаёт новую версию и новый workflow; прежняя история остаётся. После обоих исходов прежний участник не получает новую версию. [BPMN](diagrams/rejection-resubmit.bpmn). Ошибки stale revision/scan/route оставляют документ в предыдущем состоянии. FR-002/003/008.

## BP-04: управление доступом

Участники: requester/owner, CUSTODIAN, SECURITY, API, recipient. Request содержит конкретную версию, действия, цель и срок. Owner для nonrestricted может активировать сразу. RESTRICTED: PENDING, окно подтверждения 24 часа, ≤8 часов доступа от activation, два разных office/actor, без requester/recipient self-approval. Даже сохранённый ACTIVE grant не даёт право при истечении office, блокировке лица, изменении scope или trash. Отзыв доступен участникам grant и полномочным offices; terminal grant не оживляется. [BPMN](diagrams/access-management.bpmn), [ACL sequence](diagrams/access-check.mmd). FR-010…014.

## Состояния

DRAFT/REVISION_REQUIRED — editable; submit → SUBMITTED, затем start → IN_APPROVAL. Start разрешён и непосредственно из DRAFT/REVISION_REQUIRED. Workflow RUNNING → APPROVED / REJECTED / REVISION_REQUIRED / CANCELLED. cancel вне workflow: DRAFT/SUBMITTED/REVISION_REQUIRED → CANCELLED. archive: CANCELLED/APPROVED/REJECTED → ARCHIVED. Trash — deleted_at, не отдельный workflow status. Дедлайн даёт overdue view; не запускает автоматический переход.

Источник: [apps/api/app/documents.py:275](../../apps/api/app/documents.py#L275), [apps/api/app/workflows.py:315](../../apps/api/app/workflows.py#L315), [apps/api/app/access.py](../../apps/api/app/access.py).
