"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Document, WorkflowTemplate, WorkflowInstance } from "@/lib/types";
import { useI18n } from "./provider";
import { ErrorBox } from "./common";
export function Workflow({
  doc,
  busy,
  mutate,
}: {
  doc: Document;
  busy: boolean;
  mutate: (path: string, options: RequestInit) => Promise<boolean>;
}) {
  const { t, lang } = useI18n();
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([]);
  const [instances, setInstances] = useState<WorkflowInstance[]>([]);
  const [template, setTemplate] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      api<WorkflowTemplate[]>("/workflow-templates"),
      api<WorkflowInstance[]>(`/documents/${doc.id}/workflows`),
    ])
      .then(([a, b]) => {
        if (active) {
          setTemplates(a);
          setInstances(b);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.code : "error");
      });
    return () => {
      active = false;
    };
  }, [doc.id, doc.revision]);
  const owner = doc.capabilities.workflow;
  const current = instances.find((x) => x.status === "RUNNING");
  const mine = current?.approvals.find(
    (x) => x.mine && x.status === "PENDING" && x.stage === current.stage,
  );
  async function run(path: string, body: Record<string, unknown>) {
    if (
      await mutate(path, {
        method: "POST",
        body: JSON.stringify(body),
      })
    ) {
      setComment("");
    }
  }
  return (
    <section className="panel">
      <h2>{t("workflow")}</h2>
      <ErrorBox code={error} />
      {owner &&
        !doc.deleted_at &&
        !current &&
        ["DRAFT", "SUBMITTED", "REVISION_REQUIRED"].includes(doc.status) &&
        templates.length > 0 && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              run(`/documents/${doc.id}/workflows`, {
                template_id: template || templates[0].id,
                expected_revision: doc.revision,
              });
            }}
          >
            <label>
              {t("workflows")}
              <select
                value={template || templates[0].id}
                onChange={(e) => setTemplate(e.target.value)}
              >
                {templates.map((x) => (
                  <option key={x.id} value={x.id}>
                    {lang === "ru" ? x.name_ru : x.name_en} · v{x.version}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primary"
              disabled={busy || !doc.current_version_id}
            >
              {t("startWorkflow")}
            </button>
          </form>
        )}
      {current && (
        <>
          <p>
            {t(current.status)} · {t("stage")} {current.stage + 1} ·{" "}
            {lang === "ru"
              ? current.template.stages[current.stage].name_ru
              : current.template.stages[current.stage].name_en}
          </p>
          {(mine || owner) && (
            <>
              <label>
                {t("decisionComment")}
                <textarea
                  value={comment}
                  maxLength={2000}
                  onChange={(e) => setComment(e.target.value)}
                />
              </label>
              <div className="actions">
                {mine &&
                  (["approve", "reject", "revision"] as const).map((action) => (
                    <button
                      disabled={
                        busy ||
                        ((action !== "approve" ||
                          current.template.stages[current.stage]
                            .require_comment) &&
                          !comment.trim())
                      }
                      key={action}
                      onClick={() =>
                        run(`/workflows/${current.id}/decisions`, {
                          action,
                          comment,
                        })
                      }
                    >
                      {t(action === "revision" ? "returnRevision" : action)}
                    </button>
                  ))}
                {owner && (
                  <button
                    disabled={busy || !comment.trim()}
                    onClick={() =>
                      run(`/workflows/${current.id}/decisions`, {
                        action: "cancel",
                        comment,
                      })
                    }
                  >
                    {t("cancel")}
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
      {instances.length === 0 && <p>{t("empty")}</p>}
      {instances.map((instance) => (
        <details key={instance.id} open={instance.status === "RUNNING"}>
          <summary>
            {lang === "ru"
              ? instance.template.name_ru
              : instance.template.name_en}{" "}
            · v{instance.template.version} · {t(instance.status)}
          </summary>
          <p>
            {t("workflowVersion")}: {instance.document_version_id}
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("stage")}</th>
                  <th>{t("actor")}</th>
                  <th>{t("status")}</th>
                  <th>{t("dueAt")}</th>
                </tr>
              </thead>
              <tbody>
                {instance.approvals.map((a) => (
                  <tr key={a.id}>
                    <td>{lang === "ru" ? a.name_ru : a.name_en}</td>
                    <td>{a.display_name}</td>
                    <td>{t(a.status)}</td>
                    <td>
                      {a.due_at ? new Date(a.due_at).toLocaleString(lang) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <h3>{t("workflowHistory")}</h3>
          {instance.events.map((event) => (
            <article className="comment" key={event.id}>
              <strong>{t(event.action)}</strong>
              <p>{event.comment}</p>
              <small>
                {new Date(event.created_at).toLocaleString(lang)} ·{" "}
                {event.display_name} · {t(event.previous_state)} →{" "}
                {t(event.new_state)}
              </small>
            </article>
          ))}
        </details>
      ))}
    </section>
  );
}
