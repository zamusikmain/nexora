"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Activity, Catalog, Comment, Document, Version } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { useUser } from "@/components/shell";
import { Badge, ErrorBox } from "@/components/common";
export default function Page() {
  const { id } = useParams<{ id: string }>();
  const { t, lang } = useI18n();
  const user = useUser();
  const [doc, setDoc] = useState<Document | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [comments, setComments] = useState<Comment[]>([]);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [types, setTypes] = useState<Catalog[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const load = useCallback(async () => {
    const [d, v, c, a, types] = await Promise.all([
      api<Document>(`/documents/${id}`),
      api<Version[]>(`/documents/${id}/versions`),
      api<Comment[]>(`/documents/${id}/comments`),
      api<Activity[]>(`/documents/${id}/activity`),
      api<Catalog[]>("/document-types"),
    ]);
    setDoc(d);
    setVersions(v);
    setComments(c);
    setActivity(a);
    setTypes(types);
  }, [id]);
  useEffect(() => {
    Promise.all([
      api<Document>(`/documents/${id}`),
      api<Version[]>(`/documents/${id}/versions`),
      api<Comment[]>(`/documents/${id}/comments`),
      api<Activity[]>(`/documents/${id}/activity`),
      api<Catalog[]>("/document-types"),
    ])
      .then(([d, v, c, a, types]) => {
        setDoc(d);
        setVersions(v);
        setComments(c);
        setActivity(a);
        setTypes(types);
      })
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, [id]);
  const owner = doc && (doc.owner_id === user?.id || user?.role === "ADMIN");
  const editable =
    owner && ["DRAFT", "REVISION_REQUIRED"].includes(doc?.status || "");
  async function mutate(path: string, options: RequestInit) {
    setBusy(true);
    setError("");
    try {
      await api(path, options);
      await load();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
      return false;
    } finally {
      setBusy(false);
    }
  }
  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = new FormData(form);
    const file = body.get("file") as File;
    if (file.size > 20 * 1024 * 1024) {
      setError("maxFile");
      return;
    }
    if (await mutate(`/documents/${id}/versions`, { method: "POST", body }))
      form.reset();
  }
  async function comment(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = new FormData(form);
    if (
      await mutate(`/documents/${id}/comments`, {
        method: "POST",
        body: JSON.stringify({ body: body.get("body") }),
      })
    )
      form.reset();
  }
  async function save(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    let metadata;
    try {
      metadata = JSON.parse(String(data.get("metadata")));
      if (!metadata || Array.isArray(metadata) || typeof metadata !== "object")
        throw Error();
    } catch {
      setError("invalidJson");
      return;
    }
    if (
      await mutate(`/documents/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: data.get("title"),
          business_metadata: metadata,
        }),
      })
    )
      setEditing(false);
  }
  async function transition(action: string) {
    if (!window.confirm(t("confirm"))) return;
    await mutate(`/documents/${id}/transitions`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
  }
  return (
    <>
      <Link className="back" href="/documents">
        ← {t("back")}
      </Link>
      <ErrorBox code={error} />
      {!doc && !error ? (
        <p>{t("loading")}</p>
      ) : (
        doc && (
          <>
            <div className="page-heading">
              <div>
                <p className="eyebrow mono">{doc.number}</p>
                <h1>{doc.title}</h1>
                <Badge status={doc.status} />
              </div>
              <div className="actions">
                {editable && (
                  <button onClick={() => setEditing(!editing)}>
                    {t("edit")}
                  </button>
                )}
                {owner &&
                  ["DRAFT", "REVISION_REQUIRED"].includes(doc.status) && (
                    <button
                      className="primary"
                      disabled={busy || !doc.current_version_id}
                      onClick={() => transition("submit")}
                    >
                      {t("submit")}
                    </button>
                  )}
                {owner &&
                  ["DRAFT", "SUBMITTED", "REVISION_REQUIRED"].includes(
                    doc.status,
                  ) && (
                    <button
                      disabled={busy}
                      onClick={() => transition("cancel")}
                    >
                      {t("cancel")}
                    </button>
                  )}
                {owner &&
                  ["CANCELLED", "APPROVED", "REJECTED"].includes(
                    doc.status,
                  ) && (
                    <button
                      disabled={busy}
                      onClick={() => transition("archive")}
                    >
                      {t("archive")}
                    </button>
                  )}
              </div>
            </div>
            <section className="panel">
              <h2>{t("overview")}</h2>
              {editing ? (
                <form onSubmit={save}>
                  <label>
                    {t("title")}
                    <input
                      name="title"
                      defaultValue={doc.title}
                      required
                      maxLength={240}
                    />
                  </label>
                  <label>
                    {t("metadata")}
                    <textarea
                      name="metadata"
                      defaultValue={JSON.stringify(
                        doc.business_metadata,
                        null,
                        2,
                      )}
                      rows={6}
                      maxLength={16384}
                    />
                  </label>
                  <button disabled={busy} className="primary">
                    {t("save")}
                  </button>
                  <button type="button" onClick={() => setEditing(false)}>
                    {t("cancelEdit")}
                  </button>
                </form>
              ) : (
                <>
                  <dl className="details">
                    <div>
                      <dt>{t("number")}</dt>
                      <dd className="mono">{doc.number}</dd>
                    </div>
                    <div>
                      <dt>{t("type")}</dt>
                      <dd>
                        {
                          types.find((v) => v.id === doc.type_id)?.[
                            lang === "ru" ? "name_ru" : "name_en"
                          ]
                        }
                      </dd>
                    </div>
                    <div>
                      <dt>{t("registered")}</dt>
                      <dd>{new Date(doc.created_at).toLocaleString(lang)}</dd>
                    </div>
                  </dl>
                  <h3>{t("metadata")}</h3>
                  <pre>{JSON.stringify(doc.business_metadata, null, 2)}</pre>
                </>
              )}
            </section>
            <section className="panel">
              <h2>{t("versions")}</h2>
              {!versions.length && <p className="empty">{t("noVersion")}</p>}
              {versions.map((v) => (
                <div className="version" key={v.id}>
                  <div>
                    <strong>v{v.version_number}</strong>{" "}
                    <span>{v.original_filename}</span>{" "}
                    {v.id === doc.current_version_id && (
                      <span className="badge">{t("current")}</span>
                    )}
                    <p>
                      {v.size.toLocaleString(lang)} {t("bytes")} ·{" "}
                      {new Date(v.created_at).toLocaleString(lang)}
                    </p>
                    {v.change_note && <p>{v.change_note}</p>}
                    <details>
                      <summary>{t("hash")}</summary>
                      <code>{v.sha256}</code>
                    </details>
                  </div>
                  <a
                    className="button"
                    href={`/api/v1/documents/${id}/versions/${v.id}/download`}
                  >
                    {t("download")}
                  </a>
                </div>
              ))}
              {editable && (
                <form className="upload-form" onSubmit={upload}>
                  <label>
                    {t("file")}
                    <input
                      name="file"
                      type="file"
                      accept=".pdf,.docx,.txt"
                      required
                    />
                  </label>
                  <label>
                    {t("note")}
                    <input name="change_note" maxLength={1000} />
                  </label>
                  <button disabled={busy} className="primary">
                    {t(busy ? "loading" : "upload")}
                  </button>
                </form>
              )}
            </section>
            <div className="two-columns">
              <section className="panel">
                <h2>{t("comments")}</h2>
                {comments.length ? (
                  comments.map((c) => (
                    <article className="comment" key={c.id}>
                      <p>{c.body}</p>
                      <small>
                        {c.author_id.slice(0, 8)} ·{" "}
                        {new Date(c.created_at).toLocaleString(lang)}
                      </small>
                    </article>
                  ))
                ) : (
                  <p>{t("empty")}</p>
                )}
                {doc.status !== "ARCHIVED" && (
                  <form onSubmit={comment}>
                    <label>
                      {t("comment")}
                      <textarea
                        name="body"
                        rows={3}
                        maxLength={4000}
                        required
                      />
                    </label>
                    <button disabled={busy}>{t("addComment")}</button>
                  </form>
                )}
              </section>
              <section className="panel">
                <h2>{t("activity")}</h2>
                {activity.map((a) => (
                  <div className="activity" key={a.id}>
                    <span className="dot" />
                    <div>
                      <strong>{t(a.action)}</strong>
                      <small>
                        {new Date(a.created_at).toLocaleString(lang)} ·{" "}
                        {a.actor_id?.slice(0, 8)}
                      </small>
                    </div>
                  </div>
                ))}
              </section>
            </div>
          </>
        )
      )}
    </>
  );
}
