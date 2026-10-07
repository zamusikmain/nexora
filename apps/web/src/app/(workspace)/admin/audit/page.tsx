"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Activity } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
export default function Page() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<{ items: Activity[]; total: number } | null>(
    null,
  );
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ items: Activity[]; total: number }>(`/audit?page=${page}`)
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, [page]);
  return (
    <>
      <h1>{t("audit")}</h1>
      <ErrorBox code={error} />
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("activity")}</th>
                <th>{t("actor")}</th>
                <th>{t("updated")}</th>
                <th>{t("requestId")}</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((a) => (
                <tr key={a.id}>
                  <td>{t(a.action)}</td>
                  <td className="mono">{a.actor_id?.slice(0, 8) || "—"}</td>
                  <td>{new Date(a.created_at).toLocaleString(lang)}</td>
                  <td className="mono">{a.request_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data && !error && <p>{t("loading")}</p>}
        <div className="pagination">
          <span>
            {t("total")}: {data?.total || 0}
          </span>
          <div>
            <button disabled={page === 1} onClick={() => setPage(page - 1)}>
              {t("previous")}
            </button>
            <button
              disabled={page * 50 >= (data?.total || 0)}
              onClick={() => setPage(page + 1)}
            >
              {t("next")}
            </button>
          </div>
        </div>
      </section>
    </>
  );
}
