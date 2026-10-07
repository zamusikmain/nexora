"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Catalog, DocumentList } from "@/lib/types";
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
  const [data, setData] = useState<DocumentList | null>(null);
  const [types, setTypes] = useState<Catalog[]>([]);
  const [departments, setDepartments] = useState<Catalog[]>([]);
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({
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
    const params = new URLSearchParams({ ...filters, page: String(page) });
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
  }, [filters, page]);
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
        <div className="filters">
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
                    {lang === "ru" ? item.name_ru : item.name_en}
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
