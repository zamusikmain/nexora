"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Document } from "@/lib/types";
import { useI18n } from "./provider";
import { ErrorBox } from "./common";

export function AccessControls({ doc }: { doc: Document }) {
  const { t } = useI18n();
  const [people, setPeople] = useState<{ id: string; display_name: string }[]>([]);
  const [recipient, setRecipient] = useState("");
  const [reason, setReason] = useState("");
  const [hours, setHours] = useState(4);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api<{ id: string; display_name: string }[]>("/access/people").then(setPeople).catch(() => setError("error")); }, []);
  async function submit(department: boolean) {
    setBusy(true); setError(""); setMessage("");
    try {
      await api(`/documents/${doc.id}/${department ? "department-review" : "access-requests"}`, {
        method: "POST", body: JSON.stringify(department
          ? { version_id: doc.current_version_id, reason, hours }
          : { recipient_id: recipient, version_id: doc.current_version_id, actions: ["card", "file"], reason, hours }),
      });
      setMessage("accessRequestSaved");
    } catch (e) { setError(e instanceof ApiError ? e.code : "error"); }
    finally { setBusy(false); }
  }
  return <section className="panel">
    <h2>{t("documentAccess")}</h2><ErrorBox code={error} />
    {message && <p role="status">{t(message)}</p>}
    <form onSubmit={(e) => { e.preventDefault(); submit(false); }}>
      <label>{t("accessRecipient")}<select required value={recipient} onChange={(e) => setRecipient(e.target.value)}>
        <option value="">{t("selectRecipient")}</option>
        {people.filter((p) => p.id !== doc.owner_id).map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
      </select></label>
      <label>{t("accessReason")}<textarea required minLength={3} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      <label>{t("accessHours")}<input type="number" min={1} max={doc.confidentiality === "RESTRICTED" ? 8 : 168} value={hours} onChange={(e) => setHours(Number(e.target.value))} /></label>
      <button disabled={busy || !doc.current_version_id}>{t("requestAccess")}</button>
      {["PUBLIC", "INTERNAL"].includes(doc.confidentiality) && ["DRAFT", "REVISION_REQUIRED"].includes(doc.status) &&
        <button type="button" disabled={busy || reason.trim().length < 3 || !doc.current_version_id} onClick={() => submit(true)}>{t("shareDepartmentDraft")}</button>}
    </form>
    <Link href="/access">{t("accessRequests")}</Link>
  </section>;
}
