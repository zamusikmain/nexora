# Диаграммы

AS-IS текущей ветки; диаграммы — документация, не код workflow engine.

| Вид | Артефакт |
|---|---|
| BPMN: регистрация | [create-document.bpmn](create-document.bpmn) |
| BPMN: согласование | [approval.bpmn](approval.bpmn) |
| BPMN: отклонение / доработка | [rejection-resubmit.bpmn](rejection-resubmit.bpmn) |
| BPMN: управление допуском | [access-management.bpmn](access-management.bpmn) |
| UML Use Case | [use-cases.puml](use-cases.puml) |
| UML Component | [components.puml](components.puml) |
| Sequence: регистрация | [create-document.mmd](create-document.mmd) |
| Sequence: start | [start-workflow.mmd](start-workflow.mmd) |
| Sequence: decision | [decision.mmd](decision.mmd) |
| Sequence: ACL/download | [access-check.mmd](access-check.mmd) |
| ERD | [data-model.mmd](data-model.mmd) |
| Обзор, обычный flowchart | [architecture.mmd](architecture.mmd) |

BPMN XML содержит BPMN DI, lanes, events, tasks, exclusive gateways и alternate/error paths; isExecutable=false. Личные permissions и транзакции проверяются API, а не BPMN engine. В approval BPMN cancellation owner показана в тексте процесса, не как отдельный interrupting event; concurrent approvals свёрнуты в задачу и условие всех решений. Access BPMN не моделирует фоновый scheduler: expiry проверяется при запросе.

PlantUML — источник настоящей Use Case/Component notation; Mermaid sequences — сообщения сценария, flowchart — только обзор. ERD показывает FK connectivity; точную optionality и уникальность, особенно composite FK и receipt1:1, читать вместе с dictionary. Для облегчения проверки все поля ERD извлечены из metadata.

Результаты parser/editor/render проверки и ограничения приведены в [отчёте](../IMPLEMENTATION_REPORT.md). Не считать ручное чтение PlantUML полноценной render-проверкой.
