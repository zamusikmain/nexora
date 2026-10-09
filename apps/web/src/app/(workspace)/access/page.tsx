"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";

type Grant = { id: string; recipient_id: string; classification: string; reason: string; status: string;
  actions: string[]; endorsed_offices: string[]; can_endorse: boolean; scope_hash: string; version_id: string; expires_at: string | null; department_id: string | null };
type Authority = { department_id: string; office: string };
export default function Page() {
  const { t, lang } = useI18n();
  const [grants, setGrants] = useState<Grant[]>([]);
  const [offices, setOffices] = useState<Authority[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  async function load() {
    const [data, authority] = await Promise.all([api<{ items: Grant[]; total: number }>(`/access/grants?page=${page}`), api<Authority[]>("/access/authority")]);
    setGrants(data.items); setTotal(data.total); setOffices(authority);
  }
  useEffect(() => {
    let active = true;
    Promise.all([api<{ items: Grant[]; total: number }>(`/access/grants?page=${page}`), api<Authority[]>("/access/authority")])
      .then(([data, authority]) => { if (active) { setGrants(data.items); setTotal(data.total); setOffices(authority); } })
      .catch((e) => { if (active) { setGrants([]); setError(e instanceof ApiError ? e.code : "error"); } });
    return () => { active = false; };
  }, [page]);
  async function act(path: string, body: object, method = "POST") {
    setBusy(true); setError("");
    try { await api(path, { method, body: JSON.stringify(body) }); await load(); }
    catch (e) { setError(e instanceof ApiError ? e.code : "error"); }
    finally { setBusy(false); }
  }
  return <>
    <h1>{t("accessRequests")}</h1><ErrorBox code={error} />
    <label>{t("revokeReason")}<input value={reason} minLength={3} maxLength={1000} onChange={(e) => setReason(e.target.value)} /></label>
    {offices.filter((a) => a.office === "CUSTODIAN").map((a) => <section className="panel" key={a.department_id}>
      <h2>{t("departmentReviewPolicy")}</h2><p>{a.department_id}</p>
      <button disabled={busy} onClick={() => act(`/departments/${a.department_id}/review-policy`, { enabled: true }, "PUT")}>{t("enableDepartmentReview")}</button>
      <button disabled={busy} onClick={() => act(`/departments/${a.department_id}/review-policy`, { enabled: false }, "PUT")}>{t("disableDepartmentReview")}</button>
    </section>)}
    {!grants.length && <p>{t("empty")}</p>}
    {grants.map((g) => <section className="panel" key={g.id}>
      <h2>{t("accessRequest")}</h2><p>{t(g.classification)} · {t(g.status)}</p>
      <p>{g.reason}</p><p>{t("workflowVersion")}: {g.version_id}</p>
      <p>{g.actions.map((a) => t(`accessAction_${a}`)).join(", ")}</p>
      <p>{t("accessEndorsements")}: {g.endorsed_offices.map((a) => t(a)).join(", ") || "—"}</p>
      {g.expires_at && <p>{t("accessExpires")}: {new Date(g.expires_at).toLocaleString(lang)}</p>}
      {g.status === "PENDING" && g.can_endorse && offices.filter((a) => a.department_id === g.department_id && !g.endorsed_offices.includes(a.office) && (g.classification === "RESTRICTED" || a.office === "CUSTODIAN")).map((a) =>
        <button disabled={busy} key={a.office} onClick={() => act(`/access/grants/${g.id}/endorse`, { office: a.office, scope_hash: g.scope_hash })}>
          {t("endorseAccess")} · {t(a.office)}
        </button>)}
      {["PENDING", "ACTIVE"].includes(g.status) && <button disabled={busy || reason.trim().length < 3} onClick={() => act(`/access/grants/${g.id}/revoke`, { reason })}>{t("revokeAccess")}</button>}
    </section>)}
    <div className="pagination"><span>{t("total")}: {total} · {t("page")} {page}</span>
      <button disabled={page === 1 || busy} onClick={() => setPage(page - 1)}>{t("previous")}</button>
      <button disabled={page * 25 >= total || busy} onClick={() => setPage(page + 1)}>{t("next")}</button>
    </div>
  </>;
}
