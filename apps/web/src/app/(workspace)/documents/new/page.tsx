"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { Catalog, Document } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { CustomFields, collectCustomFields } from "@/components/custom-fields";
import {
  DocumentMetadata,
  collectMetadata,
} from "@/components/document-metadata";
import { ErrorBox } from "@/components/common";
export default function Page() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [types, setTypes] = useState<Catalog[]>([]);
  const [typeId, setTypeId] = useState("");
  const selected = types.find((x) => x.id === (typeId || types[0]?.id));
  const fields = selected?.metadata_schema?.fields || [];
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Catalog[]>("/document-types")
      .then(setTypes)
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    let metadata;
    try {
      metadata = fields.length
        ? collectCustomFields(form, fields)
        : JSON.parse(String(form.get("metadata")));
      if (!metadata || Array.isArray(metadata) || typeof metadata !== "object")
        throw Error();
    } catch {
      setError("invalidJson");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const doc = await api<Document>("/documents", {
        method: "POST",
        body: JSON.stringify({
          title: form.get("title"),
          type_id: form.get("type_id"),
          business_metadata: metadata,
          ...collectMetadata(form),
        }),
      });
      router.push(`/documents/${doc.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back" href="/documents">
        ← {t("back")}
      </Link>
      <h1>{t("newDocument")}</h1>
      <section className="panel form-panel">
        <form onSubmit={create}>
          <label>
            {t("title")}
            <input name="title" required maxLength={240} />
          </label>
          <label>
            {t("type")}
            <select
              name="type_id"
              required
              value={typeId || types[0]?.id || ""}
              onChange={(e) => setTypeId(e.target.value)}
            >
              {types.map((item) => (
                <option key={item.id} value={item.id}>
                  {lang === "ru" ? item.name_ru : item.name_en}
                </option>
              ))}
            </select>
          </label>
          <DocumentMetadata />
          {fields.length ? (
            <CustomFields key={selected?.id} fields={fields} />
          ) : (
            <label>
              {t("metadata")}
              <textarea
                name="metadata"
                defaultValue="{}"
                rows={7}
                maxLength={16384}
                className="mono"
              />
            </label>
          )}
          <ErrorBox code={error} />
          <button className="primary" disabled={busy || !types.length}>
            {t(busy ? "loading" : "create")}
          </button>
        </form>
      </section>
    </>
  );
}
