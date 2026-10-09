"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Document, Folder, Version } from "@/lib/types";
import { useI18n } from "./provider";
import { ErrorBox } from "./common";
export function DmsActions({
  doc,
  versions,
  busy,
  mutate,
}: {
  doc: Document;
  versions: Version[];
  busy: boolean;
  mutate: (path: string, options: RequestInit) => Promise<boolean>;
}) {
  const { t } = useI18n();
  const [folders, setFolders] = useState<Folder[]>([]);
  const [parent, setParent] = useState("");
  const [path, setPath] = useState<Folder[]>([]);
  const [diff, setDiff] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [comparing, setComparing] = useState(false);
  const owner = doc.capabilities.workflow;
  const editable =
    owner &&
    !doc.deleted_at &&
    ["DRAFT", "REVISION_REQUIRED"].includes(doc.status);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Folder[]>(`/folders${parent ? `?parent_id=${parent}` : ""}`),
      parent
        ? api<Folder[]>(`/folders/${parent}/breadcrumbs`)
        : Promise.resolve([]),
    ])
      .then(([f, p]) => {
        if (active) {
          setFolders(f.filter((x) => x.owner_id === doc.owner_id));
          setPath(p);
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.code : "error");
      });
    return () => {
      active = false;
    };
  }, [parent, doc.owner_id]);
  const post = (suffix: string) =>
    mutate(`/documents/${doc.id}/${suffix}`, {
      method: "POST",
      body: JSON.stringify({ expected_revision: doc.revision }),
    });
  async function compare(id: string) {
    setComparing(true);
    setError("");
    try {
      const result = await api<{ diff: string }>(
        `/documents/${doc.id}/versions/${id}/diff/${doc.current_version_id}`,
      );
      setDiff(result.diff);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    } finally {
      setComparing(false);
    }
  }
  return (
    <section className="panel">
      <ErrorBox code={error} />
      <div className="actions">
        <button
          disabled={busy}
          onClick={() =>
            mutate(`/documents/${doc.id}/favorite`, { method: "PUT" })
          }
        >
          {t("favorite")}
        </button>
        <button
          disabled={busy}
          onClick={() =>
            mutate(`/documents/${doc.id}/favorite`, { method: "DELETE" })
          }
        >
          {t("unfavorite")}
        </button>
        {owner &&
          (doc.deleted_at ? (
            <button disabled={busy} onClick={() => post("restore")}>
              {t("restore")}
            </button>
          ) : (
            [
              "DRAFT",
              "REVISION_REQUIRED",
              "CANCELLED",
              "REJECTED",
              "ARCHIVED",
            ].includes(doc.status) && (
              <button
                disabled={busy}
                onClick={() => {
                  if (window.confirm(t("confirm"))) post("trash");
                }}
              >
                {t("trash")}
              </button>
            )
          ))}
      </div>
      {editable && (
        <details>
          <summary>{t("move")}</summary>
          <nav aria-label={t("folders")} className="actions">
            <button onClick={() => setParent("")}>{t("rootFolder")}</button>
            {path.map((f) => (
              <button key={f.id} onClick={() => setParent(f.id)}>
                {f.name}
              </button>
            ))}
          </nav>
          <div className="actions">
            {folders.map((f) => (
              <button key={f.id} onClick={() => setParent(f.id)}>
                {f.name}
              </button>
            ))}
          </div>
          <button
            disabled={busy}
            onClick={() =>
              mutate(`/documents/${doc.id}/move`, {
                method: "POST",
                body: JSON.stringify({
                  folder_id: parent || null,
                  expected_revision: doc.revision,
                }),
              })
            }
          >
            {t("move")}
          </button>
        </details>
      )}
      {versions
        .filter((v) => v.id !== doc.current_version_id)
        .map((v) => (
          <div className="actions" key={v.id}>
            <span>v{v.version_number}</span>
            {editable && (
              <button
                disabled={busy}
                onClick={() => {
                  if (window.confirm(t("confirm")))
                    post(`versions/${v.id}/restore`);
                }}
              >
                {t("restoreVersion")}
              </button>
            )}
            {doc.capabilities.compare && v.mime_type === "text/plain" &&
              versions.find((x) => x.id === doc.current_version_id)
                ?.mime_type === "text/plain" && (
                <button disabled={comparing} onClick={() => compare(v.id)}>
                  {t("compareVersion")}
                </button>
              )}
          </div>
        ))}
      {diff !== null && (
        <details open>
          <summary>{t("diff")}</summary>
          <pre>{diff || t("empty")}</pre>
        </details>
      )}
    </section>
  );
}
