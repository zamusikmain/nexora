"use client";
import { Document } from "@/lib/types";
import { useI18n } from "./provider";
export function DocumentMetadata({ doc }: { doc?: Document }) {
  const { t } = useI18n();
  return (
    <fieldset>
      <legend>{t("overview")}</legend>
      <label>
        {t("description")}
        <textarea
          name="description"
          defaultValue={doc?.description || ""}
          maxLength={4000}
        />
      </label>
      <label>
        {t("category")}
        <input
          name="category"
          defaultValue={doc?.category || ""}
          maxLength={100}
        />
      </label>
      <label>
        {t("tags")}
        <input
          name="tags"
          defaultValue={doc?.tags.join(", ") || ""}
          maxLength={1530}
        />
      </label>
      <label>
        {t("responsible")}
        <input
          name="responsible_id"
          defaultValue={doc?.responsible_id || ""}
          maxLength={36}
        />
      </label>
      <label>
        {t("confidentiality")}
        <select
          name="confidentiality"
          defaultValue={doc?.confidentiality || "INTERNAL"}
        >
          {["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"].map((x) => (
            <option key={x} value={x}>
              {t(x)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("effectiveDate")}
        <input
          name="effective_date"
          type="date"
          defaultValue={doc?.effective_date || ""}
        />
      </label>
      <label>
        {t("expirationDate")}
        <input
          name="expiration_date"
          type="date"
          defaultValue={doc?.expiration_date || ""}
        />
      </label>
    </fieldset>
  );
}
export function collectMetadata(form: FormData) {
  return {
    description: form.get("description"),
    category: form.get("category"),
    tags: String(form.get("tags") || "")
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
    responsible_id: form.get("responsible_id") || null,
    confidentiality: form.get("confidentiality"),
    effective_date: form.get("effective_date") || null,
    expiration_date: form.get("expiration_date") || null,
  };
}
