"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Document, Version } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";

type View = {
  kind: string; id: string; can_decide?: boolean; instance_id?: string;
  status: string; outcome?: string; acted_at?: string; version_id?: string;
  can_request_snapshot?: boolean; snapshot_available?: boolean; snapshot?: { title: string; own_comment: string; version_id: string };
  document?: Document; version?: Version; stage?: { name_ru: string; name_en: string; require_comment: boolean };
};
export default function Page() {
  const { id, view } = useParams<{ id: string; view: string }>();
  const router = useRouter();
  const { t, lang } = useI18n();
  const [data, setData] = useState<View | null>(null);
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef({ value: 0 });
  const load = useCallback(async () => {
    const current = ++generation.current.value;
    try {
      const result = await api<View>(`/approvals/${id}/${view === "receipt" ? "receipt" : "review"}`);
      if (current === generation.current.value) { setData(result); setError(""); }
    } catch (e) { if (current === generation.current.value) { setData(null); setComment(""); setError(e instanceof ApiError ? e.code : "error"); } }
  }, [id, view]);
  useEffect(() => {
    const counter = generation.current;
    const initial = window.setTimeout(load, 0); const timer = window.setInterval(load, 20000);
    window.addEventListener("focus", load);
    return () => { counter.value++; window.clearTimeout(initial); window.clearInterval(timer); window.removeEventListener("focus", load); };
  }, [load]);
  async function decide(action: string) {
    if (!data?.instance_id) return;
    setBusy(true); setError("");
    try {
      await api(`/workflows/${data.instance_id}/decisions`, { method: "POST",
        body: JSON.stringify({ action, comment }) });
      generation.current.value++; setData(null); setComment(""); router.push(`/approvals/${id}/receipt`);
    } catch (e) {
      if (e instanceof ApiError && [403, 404].includes(e.status)) { setData(null); setComment(""); }
      setError(e instanceof ApiError ? e.code : "error");
    } finally { setBusy(false); }
  }
  async function requestAccess() {
    setBusy(true); setError("");
    try {
      await api(`/approvals/${id}/access-requests`, { method: "POST", body: JSON.stringify({ reason, hours: 4,
        ...(view === "receipt" ? { purpose: "audit_snapshot", actions: ["snapshot"] } : {}) }) });
      setMessage("accessRequestSaved");
    } catch (e) { setError(e instanceof ApiError ? e.code : "error"); }
    finally { setBusy(false); }
  }
  return <>
    <Link href="/approvals">← {t("approvals")}</Link><ErrorBox code={error} />
    {!data && !error && <p>{t("loading")}</p>}
    {data?.kind === "access_required" && <section className="panel">
      <h1>{t("accessRequired")}</h1><p>{t("restrictedTask")}</p>
      {message && <p role="status">{t(message)}</p>}
      <form onSubmit={(e) => { e.preventDefault(); requestAccess(); }}>
        <label>{t("accessReason")}<textarea required minLength={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button disabled={busy}>{t("requestAccess")}</button>
      </form><button onClick={load}>{t("refreshAccess")}</button><Link href="/access">{t("accessRequests")}</Link>
    </section>}
    {data?.kind === "active_task" && data.document && data.version && <section className="panel">
      <h1>{data.document.title}</h1><p>{data.stage?.[lang !== "en" ? "name_ru" : "name_en"]}</p>
      <p>{t("workflowVersion")}: {data.version.version_number}</p><p>{data.version.original_filename}</p>
      <pre>{JSON.stringify(data.document.business_metadata, null, 2)}</pre>
      <a className="button" href={`/api/v1/documents/${data.document.id}/versions/${data.version.id}/download`}>{t("download")}</a>
      <label>{t("decisionComment")}<textarea maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} /></label>
      <div className="actions">{["approve", "reject", "revision"].map((action) =>
        <button key={action} disabled={busy || ((action !== "approve" || data.stage?.require_comment) && !comment.trim())} onClick={() => decide(action)}>
          {t(action === "revision" ? "returnRevision" : action)}
        </button>)}</div>
    </section>}
    {data && ["receipt", "cancelled"].includes(data.kind) && <section className="panel">
      <h1>{t(data.kind === "receipt" ? "reviewReceipt" : "cancelledTask")}</h1>
      <p>{t(data.outcome || data.status)}</p>
      {data.acted_at && <p>{new Date(data.acted_at).toLocaleString(lang)}</p>}
      {data.version_id && <p>{t("workflowVersion")}: {data.version_id}</p>}
      {data.snapshot ? <><h2>{t("ownReviewSnapshot")}</h2><p>{data.snapshot.title}</p><p>{data.snapshot.own_comment}</p></>
        : <p>{t("snapshotUnavailable")}</p>}
      <p>{t("receiptNoFile")}</p>
      {data.can_request_snapshot && !data.snapshot && <form onSubmit={(e) => { e.preventDefault(); requestAccess(); }}>
        <label>{t("accessReason")}<textarea required minLength={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
        <button disabled={busy}>{t("requestSnapshotAccess")}</button>
        {message && <p role="status">{t(message)}</p>}
        <Link href="/access">{t("accessRequests")}</Link>
      </form>}
    </section>}
  </>;
}
