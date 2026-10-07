"use client";
import { CustomField } from "@/lib/types";
import { useI18n } from "./provider";
export function CustomFields({
  fields,
  values = {},
}: {
  fields: CustomField[];
  values?: Record<string, unknown>;
}) {
  const { t, lang } = useI18n();
  return (
    <fieldset>
      <legend>{t("customFields")}</legend>
      {fields
        .filter((f) => f.enabled)
        .sort((a, b) => a.order - b.order)
        .map((f) => {
          const name = `custom:${f.key}`;
          const value = values[f.key] ?? f.default;
          return (
            <label key={f.key}>
              {lang === "ru" ? f.name_ru : f.name_en}
              {f.required ? " *" : ""}
              {f.kind === "boolean" ? (
                <input
                  name={name}
                  type="checkbox"
                  defaultChecked={value === true}
                />
              ) : f.kind === "select" || f.kind === "multi-select" ? (
                <select
                  name={name}
                  required={f.required}
                  multiple={f.kind === "multi-select"}
                  defaultValue={
                    f.kind === "multi-select"
                      ? Array.isArray(value)
                        ? value.map(String)
                        : []
                      : String(value ?? "")
                  }
                >
                  <option value="">{t("all")}</option>
                  {f.options.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              ) : f.kind === "textarea" ? (
                <textarea
                  name={name}
                  required={f.required}
                  maxLength={f.max_length}
                  defaultValue={String(value ?? "")}
                />
              ) : (
                <input
                  name={name}
                  required={f.required}
                  maxLength={f.max_length}
                  type={
                    f.kind === "number"
                      ? "number"
                      : f.kind === "date"
                        ? "date"
                        : f.kind === "URL"
                          ? "url"
                          : "text"
                  }
                  step={f.kind === "number" ? "any" : undefined}
                  min={f.minimum ?? undefined}
                  max={f.maximum ?? undefined}
                  defaultValue={String(value ?? "")}
                />
              )}
            </label>
          );
        })}
    </fieldset>
  );
}
export function collectCustomFields(
  form: FormData,
  fields: CustomField[],
  existing: Record<string, unknown> = {},
) {
  const values = { ...existing };
  for (const field of fields.filter((f) => f.enabled)) {
    const raw = form.get(`custom:${field.key}`);
    const text = String(raw ?? "");
    values[field.key] =
      field.kind === "boolean"
        ? raw === "on"
        : field.kind === "number"
          ? text === ""
            ? null
            : Number(text)
          : field.kind === "multi-select"
            ? form.getAll(`custom:${field.key}`).map(String).filter(Boolean)
            : text || null;
  }
  return values;
}
