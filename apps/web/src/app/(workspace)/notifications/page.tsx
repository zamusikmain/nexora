"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
import { NotificationPage } from "@/lib/types";

const PAGE = 20;

export default function Page() {
  const { t, lang } = useI18n();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<NotificationPage | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const load = useCallback(
    () =>
      api<NotificationPage>(`/notifications?unread=${unreadOnly}&page=${page}`)
        .then((x) => {
          setData(x);
          setError("");
        })
        .catch((e) => setError(e instanceof ApiError ? e.code : "error"))
        .finally(() => setBusy(false)),
    [unreadOnly, page],
  );
  useEffect(() => {
    load();
  }, [load]);
  async function mark(path: string) {
    try {
      await api(path, { method: "POST" });
      window.dispatchEvent(new Event("nexora-notifications"));
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    }
  }
  const date = (value: string) => new Date(value).toLocaleString(lang);
  return (
    <>
      <div className="page-heading">
        <h1>{t("notifications")}</h1>
        <button disabled={!data?.unread} onClick={() => mark("/notifications/read-all")}>
          {t("markAllRead")}
        </button>
      </div>
      <section className="panel">
        <label className="check">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => {
              setUnreadOnly(e.target.checked);
              setPage(1);
              setBusy(true);
            }}
          />
          {t("unreadOnly")}
        </label>
        <ErrorBox code={error} />
        {busy ? (
          <p role="status">{t("loading")}</p>
        ) : data?.items.length ? (
          <ul className="notifications">
            {data.items.map((n) => (
              <li key={n.id} className={n.read_at ? "" : "unread"}>
                <div>
                  <strong>{t("notice_" + n.kind)}</strong>
                  <p>
                    {n.document ? (
                      <>
                        {n.document.number} · {n.document.title}
                      </>
                    ) : (
                      t("documentHidden")
                    )}
                  </p>
                  <small>
                    {date(n.created_at)}
                    {n.actor_name && <> · {t("actor")}: {n.actor_name}</>}
                    {n.data.assignee_name && <> · {t("assignee")}: {n.data.assignee_name}</>}
                    {n.data.due_at && <> · {t("dueAt")}: {date(n.data.due_at)}</>}
                  </small>
                </div>
                <div className="actions">
                  {n.href && (
                    <Link
                      href={n.href}
                      onClick={() => {
                        if (!n.read_at) void api(`/notifications/${n.id}/read`, { method: "POST" }).catch(() => undefined);
                      }}
                    >
                      {t("open")}
                    </Link>
                  )}
                  {!n.read_at && (
                    <button className="quiet" onClick={() => mark(`/notifications/${n.id}/read`)}>
                      {t("markRead")}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
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
            disabled={busy || page * PAGE >= (data?.total || 0)}
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
