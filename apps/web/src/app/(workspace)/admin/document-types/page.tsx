"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Catalog, CustomField } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
const kinds = [
  "text",
  "textarea",
  "number",
  "date",
  "datetime",
  "boolean",
  "select",
  "multi-select",
  "user",
  "department",
  "URL",
];
const blank = (): CustomField => ({
  key: "",
  name_ru: "",
  name_en: "",
  kind: "text",
  required: false,
  enabled: true,
  default: null,
  options: [],
  order: 0,
  minimum: null,
  maximum: null,
  max_length: 2000,
});
export default function Page() {
  const { t, lang } = useI18n();
  const [items, setItems] = useState<Catalog[]>([]);
  const [selected, setSelected] = useState<Catalog | null>(null);
  const [fields, setFields] = useState<CustomField[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [formKey, setFormKey] = useState(0);
  useEffect(() => {
    api<Catalog[]>("/document-types")
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  function choose(item: Catalog | null) {
    setSelected(item);
    setFields(item?.metadata_schema?.fields || []);
    setFormKey((x) => x + 1);
    setError("");
  }
  function patch(index: number, value: Partial<CustomField>) {
    setFields((f) => f.map((x, i) => (i === index ? { ...x, ...value } : x)));
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const body = {
        ...(selected ? { expected_updated_at: selected.updated_at } : {}),
        code: form.get("code"),
        name_ru: form.get("name_ru"),
        name_en: form.get("name_en"),
        fields: fields.map((f, i) => ({ ...f, order: i })),
      };
      await api(
        selected ? `/document-types/${selected.id}` : "/document-types",
        { method: selected ? "PATCH" : "POST", body: JSON.stringify(body) },
      );
      setItems(await api<Catalog[]>("/document-types"));
      choose(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>{t("documentTypes")}</h1>
      <ErrorBox code={error} />
      <section className="panel">
        <div className="actions">
          <button disabled={busy} onClick={() => choose(null)}>
            {t("create")}
          </button>
          {items.map((x) => (
            <button disabled={busy} key={x.id} onClick={() => choose(x)}>
              {lang !== "en" ? x.name_ru : x.name_en}
            </button>
          ))}
        </div>
      </section>
      <section className="panel">
        <form key={formKey} onSubmit={save}>
          {(["code", "name_ru", "name_en"] as const).map((key, i) => (
            <label key={key}>
              {t(["code", "nameRu", "nameEn"][i])}
              <input
                name={key}
                defaultValue={selected?.[key] || ""}
                required
                maxLength={i ? 100 : 40}
                pattern={i ? undefined : "[A-Z][A-Z0-9_]*"}
              />
            </label>
          ))}
          <h2>{t("customFields")}</h2>
          {fields.map((f, i) => (
            <fieldset key={i}>
              <legend>{i + 1}</legend>
              <label>
                {t("fieldKey")}
                <input
                  value={f.key}
                  onChange={(e) => patch(i, { key: e.target.value })}
                  required
                  maxLength={40}
                  pattern="[a-z][a-z0-9_]*"
                />
              </label>
              {(["name_ru", "name_en"] as const).map((key, j) => (
                <label key={key}>
                  {t(j ? "nameEn" : "nameRu")}
                  <input
                    value={f[key]}
                    required
                    maxLength={100}
                    onChange={(e) => patch(i, { [key]: e.target.value })}
                  />
                </label>
              ))}
              <label>
                {t("fieldKind")}
                <select
                  value={f.kind}
                  onChange={(e) => patch(i, { kind: e.target.value })}
                >
                  {kinds.map((k) => (
                    <option key={k} value={k}>
                      {t(`field_${k}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("requiredField")}
                <input
                  type="checkbox"
                  checked={f.required}
                  onChange={(e) => patch(i, { required: e.target.checked })}
                />
              </label>
              <label>
                {t("enabledField")}
                <input
                  type="checkbox"
                  checked={f.enabled}
                  onChange={(e) => patch(i, { enabled: e.target.checked })}
                />
              </label>
              {["select", "multi-select"].includes(f.kind) && (
                <label>
                  {t("fieldOptions")}
                  <textarea
                    value={f.options.join("\n")}
                    onChange={(e) =>
                      patch(i, { options: e.target.value.split("\n") })
                    }
                  />
                </label>
              )}
              <label>
                {t("fieldDefault")}
                <input
                  defaultValue={
                    f.default === null ? "" : JSON.stringify(f.default)
                  }
                  onBlur={(e) => {
                    try {
                      patch(i, {
                        default: e.target.value
                          ? JSON.parse(e.target.value)
                          : null,
                      });
                      e.target.setCustomValidity("");
                    } catch {
                      e.target.setCustomValidity(t("invalidJson"));
                    }
                  }}
                />
              </label>
              {f.kind === "number" &&
                (["minimum", "maximum"] as const).map((key) => (
                  <label key={key}>
                    {t(key === "minimum" ? "fieldMinimum" : "fieldMaximum")}
                    <input
                      type="number"
                      step="any"
                      value={f[key] ?? ""}
                      onChange={(e) =>
                        patch(i, {
                          [key]:
                            e.target.value === ""
                              ? null
                              : Number(e.target.value),
                        })
                      }
                    />
                  </label>
                ))}
              <label>
                {t("fieldLength")}
                <input
                  type="number"
                  min={1}
                  max={4000}
                  required
                  value={f.max_length}
                  onChange={(e) =>
                    patch(i, { max_length: Number(e.target.value) })
                  }
                />
              </label>
              <button
                type="button"
                onClick={() => setFields((x) => x.filter((_, j) => i !== j))}
              >
                {t("removeField")}
              </button>
            </fieldset>
          ))}
          <div className="actions">
            <button
              type="button"
              disabled={fields.length >= 50 || busy}
              onClick={() => setFields((x) => [...x, blank()])}
            >
              {t("addField")}
            </button>
            <button className="primary" disabled={busy}>
              {t("save")}
            </button>
          </div>
        </form>
      </section>
    </>
  );
}
