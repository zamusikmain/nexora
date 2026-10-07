"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
type Result = {
  total: number;
  items: {
    id: string;
    document_id: string;
    title: string;
    number: string;
    status: string;
    due_at: string | null;
  }[];
};
export default function Page() {
  const { t, lang } = useI18n();
  const [view, setView] = useState("pending");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  useEffect(() => {
    let active = true;
    api<Result>(`/approvals?view=${view}&page=${page}`)
      .then((x) => {
        if (active) {
          setData(x);
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
  }, [view, page]);
  return (
    <>
      <h1>{t("approvals")}</h1>
      <section className="panel">
        <label>
          {t("view")}
          <select
            value={view}
            onChange={(e) => {
              setView(e.target.value);
              setPage(1);
              setBusy(true);
            }}
          >
            {["pending", "completed", "rejected", "overdue"].map((v) => (
              <option key={v} value={v}>
                {t(v)}
              </option>
            ))}
          </select>
        </label>
        <ErrorBox code={error} />
        {busy ? (
          <p role="status">{t("loading")}</p>
        ) : data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t("number")}</th>
                  <th>{t("title")}</th>
                  <th>{t("status")}</th>
                  <th>{t("dueAt")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((x) => (
                  <tr key={x.id}>
                    <td>{x.number}</td>
                    <td>
                      <Link href={`/documents/${x.document_id}`}>
                        {x.title}
                      </Link>
                    </td>
                    <td>{t(x.status)}</td>
                    <td>
                      {x.due_at ? new Date(x.due_at).toLocaleString(lang) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>{t("empty")}</p>
        )}
        <div className="pagination">
          <span>
            {t("total")}: {data?.total || 0} · {t("page")} {page}
          </span>
          <button
            disabled={busy || page === 1}
            onClick={() => {
              setPage((x) => x - 1);
              setBusy(true);
            }}
          >
            {t("previous")}
          </button>
          <button
            disabled={busy || page * 25 >= (data?.total || 0)}
            onClick={() => {
              setPage((x) => x + 1);
              setBusy(true);
            }}
          >
            {t("next")}
          </button>
        </div>
      </section>
    </>
  );
}
