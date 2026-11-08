"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Catalog, DocumentList, Folder } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { DocumentTable, ErrorBox } from "@/components/common";
const statuses = [
  "DRAFT",
  "SUBMITTED",
  "IN_REVIEW",
  "IN_APPROVAL",
  "REVISION_REQUIRED",
  "APPROVED",
  "REJECTED",
  "CANCELLED",
  "ARCHIVED",
];
export default function Page() {
  const { t, lang } = useI18n();
  const [folderId, setFolderId] = useState("");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [crumbs, setCrumbs] = useState<Folder[]>([]);
  const [folderRefresh, setFolderRefresh] = useState(0);
  const [folderBusy, setFolderBusy] = useState(false);
  const [data, setData] = useState<DocumentList | null>(null);
  const [types, setTypes] = useState<Catalog[]>([]);
  const [departments, setDepartments] = useState<Catalog[]>([]);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({
    view: "all",
    q: "",
    status: "",
    type_id: "",
    department_id: "",
  });
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(true);
  const [query, setQuery] = useState("");
  useEffect(() => {
    Promise.all([
      api<Catalog[]>("/document-types"),
      api<Catalog[]>("/departments"),
    ])
      .then(([a, b]) => {
        setTypes(a);
        setDepartments(b);
      })
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({
      ...filters,
      folder_id: folderId,
      page: String(page),
    });
    api<DocumentList>(`/documents?${params}`)
      .then((value) => {
        if (active) {
          setData(value);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.code : "error");
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [filters, page, folderId]);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Folder[]>(`/folders${folderId ? `?parent_id=${folderId}` : ""}`),
      folderId
        ? api<Folder[]>(`/folders/${folderId}/breadcrumbs`)
        : Promise.resolve([]),
    ])
      .then(([f, c]) => {
        if (active) {
          setFolders(f);
          setCrumbs(c);
        }
      })
      .catch((e) => {
        if (active) setError(e instanceof ApiError ? e.code : "error");
      });
    return () => {
      active = false;
    };
  }, [folderId, folderRefresh]);
  function navigateFolder(id: string) {
    setBusy(true);
    setPage(1);
    setFolderId(id);
  }
  async function saveFolder(
    e: React.FormEvent<HTMLFormElement>,
    edit: boolean,
  ) {
    e.preventDefault();
    const form = e.currentTarget;
    const values = new FormData(form);
    setFolderBusy(true);
    setError("");
    try {
      await api(edit ? `/folders/${folderId}` : "/folders", {
        method: edit ? "PATCH" : "POST",
        body: JSON.stringify({
          name: values.get("name"),
          parent_id: edit
            ? String(values.get("parent_id") || "") || null
            : folderId || null,
        }),
      });
      setFolderRefresh((x) => x + 1);
      form.reset();
      if (edit) navigateFolder(String(values.get("parent_id") || ""));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    } finally {
      setFolderBusy(false);
    }
  }
  function filter(key: string, value: string) {
    setBusy(true);
    setPage(1);
    setFilters((current) => ({ ...current, [key]: value }));
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">NEXORA / {t("workspace")}</p>
          <h1>{t("documents")}</h1>
        </div>
        <Link className="primary button" href="/documents/new">
          + {t("newDocument")}
        </Link>
      </div>
      <section className="panel">
        <h2>{t("folders")}</h2>
        <nav aria-label={t("folders")} className="actions">
          <button onClick={() => navigateFolder("")}>{t("rootFolder")}</button>
          {crumbs.map((f) => (
            <button key={f.id} onClick={() => navigateFolder(f.id)}>
              {f.name}
            </button>
          ))}
        </nav>
        <div className="actions">
          {folders.map((f) => (
            <button key={f.id} onClick={() => navigateFolder(f.id)}>
              {f.name}
            </button>
          ))}
        </div>
        <details>
          <summary>{t("newFolder")}</summary>
          <form onSubmit={(e) => saveFolder(e, false)}>
            <label>
              {t("folderName")}
              <input name="name" required maxLength={120} />
            </label>
            <button disabled={folderBusy}>{t("save")}</button>
          </form>
        </details>
        {folderId && (
          <details>
            <summary>{t("renameMoveFolder")}</summary>
            <form key={folderId} onSubmit={(e) => saveFolder(e, true)}>
              <label>
                {t("folderName")}
                <input
                  name="name"
                  required
                  defaultValue={crumbs.at(-1)?.name}
                  maxLength={120}
                />
              </label>
              <label>
                {t("parentFolder")}
                <select name="parent_id" defaultValue={crumbs.at(-2)?.id || ""}>
                  <option value="">{t("rootFolder")}</option>
                  {crumbs.slice(0, -1).map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </select>
              </label>
              <button disabled={folderBusy}>{t("save")}</button>
            </form>
          </details>
        )}
      </section>
      <section className="panel">
        <div className="filters">
          <label>
            {t("view")}
            <select
              value={filters.view}
              onChange={(e) => filter("view", e.target.value)}
            >
              {["all", "my", "favorites", "archive", "trash"].map((v) => (
                <option key={v} value={v}>
                  {t(`view_${v}`)}
                </option>
              ))}
            </select>
          </label>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              filter("q", query);
            }}
          >
            <input
              aria-label={t("search")}
              placeholder={t("search")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={240}
            />
            <button>{t("searchAction")}</button>
          </form>
          <label>
            {t("status")}
            <select
              value={filters.status}
              onChange={(e) => filter("status", e.target.value)}
            >
              <option value="">{t("all")}</option>
              {statuses.map((s) => (
                <option key={s} value={s}>
                  {t(s)}
                </option>
              ))}
            </select>
          </label>
          {(
            [
              ["type_id", types, "type"],
              ["department_id", departments, "department"],
            ] as const
          ).map(([key, items, label]) => (
            <label key={key}>
              {t(label)}
              <select
                value={filters[key]}
                onChange={(e) => filter(key, e.target.value)}
              >
                <option value="">{t("all")}</option>
                {items.map((item) => (
                  <option key={item.id} value={item.id}>
                    {lang !== "en" ? item.name_ru : item.name_en}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <ErrorBox code={error} />
        {busy ? (
          <p role="status">{t("loading")}</p>
        ) : (
          data && <DocumentTable items={data.items} />
        )}
        <div className="pagination">
          <span>
            {t("total")}: {data?.total || 0} · {t("page")} {page}
          </span>
          <div>
            <button
              disabled={page === 1 || busy}
              onClick={() => {
                setBusy(true);
                setPage(page - 1);
              }}
            >
              {t("previous")}
            </button>
            <button
              disabled={busy || page * 25 >= (data?.total || 0)}
              onClick={() => {
                setBusy(true);
                setPage(page + 1);
              }}
            >
              {t("next")}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
