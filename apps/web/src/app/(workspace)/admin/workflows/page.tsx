"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Catalog, User, WorkflowStage, WorkflowTemplate } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
const roles = ["USER", "REVIEWER", "APPROVER", "LEGAL", "MANAGER", "ADMIN"];
const blank = (): WorkflowStage => ({
  name_ru: "",
  name_en: "",
  selector: "user",
  targets: [],
  due_hours: 72,
  require_comment: false,
  conditions: [],
});
export default function Page() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState<WorkflowTemplate[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Catalog[]>([]);
  const [selected, setSelected] = useState<WorkflowTemplate | null>(null);
  const [stages, setStages] = useState<WorkflowStage[]>([blank()]);
  const [formKey, setFormKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([
      api<WorkflowTemplate[]>("/workflow-templates"),
      api<User[]>("/users"),
      api<Catalog[]>("/departments"),
    ])
      .then(([a, b, c]) => {
        setItems(a);
        setUsers(b.filter((x) => x.status === "ACTIVE"));
        setDepartments(c);
      })
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  function patch(i: number, values: Partial<WorkflowStage>) {
    setStages((s) => s.map((x, j) => (i === j ? { ...x, ...values } : x)));
  }
  function choose(item: WorkflowTemplate | null) {
    setSelected(item);
    setStages(item?.stages.map((x) => ({ ...x })) || [blank()]);
    setFormKey((x) => x + 1);
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      const prepared = stages.map((s, i) => {
        const field = String(data.get(`conditionField:${i}`) || "");
        return {
          ...s,
          conditions: field
            ? [
                {
                  field,
                  op: String(data.get(`conditionOp:${i}`)),
                  value: JSON.parse(String(data.get(`conditionValue:${i}`))),
                },
              ]
            : [],
        };
      });
      await api("/workflow-templates", {
        method: "POST",
        body: JSON.stringify({
          code: data.get("code"),
          name_ru: data.get("name_ru"),
          name_en: data.get("name_en"),
          stages: prepared,
        }),
      });
      setItems(await api<WorkflowTemplate[]>("/workflow-templates"));
      choose(null);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.code
          : e instanceof SyntaxError
            ? "invalidJson"
            : "error",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>{t("workflows")}</h1>
      <ErrorBox code={error} />
      <section className="panel">
        <div className="actions">
          <button disabled={busy} onClick={() => choose(null)}>
            {t("create")}
          </button>
          {items.map((x) => (
            <button disabled={busy} key={x.id} onClick={() => choose(x)}>
              {lang === "ru" ? x.name_ru : x.name_en} · v{x.version}
            </button>
          ))}
        </div>
      </section>
      <section className="panel">
        <form key={formKey} onSubmit={save}>
          {(["code", "name_ru", "name_en"] as const).map((key, i) => (
            <label key={key}>
              {t(["templateCode", "nameRu", "nameEn"][i])}
              <input
                name={key}
                required
                maxLength={i ? 120 : 40}
                pattern={i ? undefined : "[A-Z][A-Z0-9_]*"}
                defaultValue={selected?.[key] || ""}
              />
            </label>
          ))}
          {stages.map((stage, i) => (
            <fieldset key={i}>
              <legend>
                {t("stage")} {i + 1}
              </legend>
              {(["name_ru", "name_en"] as const).map((key, j) => (
                <label key={key}>
                  {t(j ? "nameEn" : "nameRu")}
                  <input
                    required
                    maxLength={100}
                    value={stage[key]}
                    onChange={(e) => patch(i, { [key]: e.target.value })}
                  />
                </label>
              ))}
              <label>
                {t("selector")}
                <select
                  value={stage.selector}
                  onChange={(e) =>
                    patch(i, { selector: e.target.value, targets: [] })
                  }
                >
                  {["user", "role", "department"].map((s) => (
                    <option key={s} value={s}>
                      {t(`selector_${s}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("targets")}
                <select
                  multiple
                  required
                  value={stage.targets}
                  onChange={(e) =>
                    patch(i, {
                      targets: Array.from(
                        e.target.selectedOptions,
                        (x) => x.value,
                      ),
                    })
                  }
                >
                  {stage.selector === "user"
                    ? users.map((u) => (
                        <option key={u.id} value={u.id}>
                          {u.display_name} · {u.email}
                        </option>
                      ))
                    : stage.selector === "role"
                      ? roles.map((r) => (
                          <option key={r} value={r}>
                            {t(r)}
                          </option>
                        ))
                      : departments.map((d) => (
                          <option key={d.id} value={d.id}>
                            {lang === "ru" ? d.name_ru : d.name_en}
                          </option>
                        ))}
                </select>
              </label>
              <label>
                {t("dueHours")}
                <input
                  type="number"
                  min={1}
                  max={720}
                  required
                  value={stage.due_hours}
                  onChange={(e) =>
                    patch(i, { due_hours: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                {t("requireComment")}
                <input
                  type="checkbox"
                  checked={stage.require_comment}
                  onChange={(e) =>
                    patch(i, { require_comment: e.target.checked })
                  }
                />
              </label>
              <label>
                {t("conditionField")}
                <input
                  name={`conditionField:${i}`}
                  maxLength={49}
                  defaultValue={stage.conditions[0]?.field || ""}
                />
              </label>
              <label>
                {t("conditionOp")}
                <select
                  name={`conditionOp:${i}`}
                  defaultValue={stage.conditions[0]?.op || "eq"}
                >
                  {["eq", "ne", "gt", "gte", "lt", "lte", "in"].map((x) => (
                    <option key={x} value={x}>
                      {t(`op_${x}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("conditionValue")}
                <input
                  name={`conditionValue:${i}`}
                  maxLength={2000}
                  defaultValue={
                    stage.conditions[0]
                      ? JSON.stringify(stage.conditions[0].value)
                      : ""
                  }
                />
              </label>
              <button
                type="button"
                disabled={stages.length === 1}
                onClick={() => setStages((x) => x.filter((_, j) => i !== j))}
              >
                {t("removeStage")}
              </button>
            </fieldset>
          ))}
          <div className="actions">
            <button
              type="button"
              disabled={busy || stages.length >= 20}
              onClick={() => setStages((x) => [...x, blank()])}
            >
              {t("addStage")}
            </button>
            <button className="primary" disabled={busy}>
              {t("newTemplateVersion")}
            </button>
          </div>
        </form>
      </section>
    </>
  );
}
