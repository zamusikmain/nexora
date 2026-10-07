"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
type Session = {
  id: string;
  user_agent: string;
  created_at: string;
  expires_at: string;
  current: boolean;
};
export default function Page() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Session[]>("/auth/sessions")
      .then(setSessions)
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  async function revoke(session?: Session) {
    if (!window.confirm(t("confirm"))) return;
    setBusy(true);
    setError("");
    try {
      await api(
        session
          ? `/auth/sessions/${session.id}`
          : "/auth/sessions/revoke-others",
        { method: session ? "DELETE" : "POST" },
      );
      if (session?.current) {
        router.replace("/login");
        return;
      }
      setSessions(await api<Session[]>("/auth/sessions"));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>{t("securitySessions")}</h1>
      <ErrorBox code={error} />
      <section className="panel">
        <button disabled={busy} onClick={() => revoke()}>
          {t("revokeOtherSessions")}
        </button>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("device")}</th>
                <th>{t("registered")}</th>
                <th>{t("sessionExpires")}</th>
                <th>{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td>
                    {s.user_agent || t("unknownDevice")}
                    {s.current && <span className="badge">{t("current")}</span>}
                  </td>
                  <td>{new Date(s.created_at).toLocaleString(lang)}</td>
                  <td>{new Date(s.expires_at).toLocaleString(lang)}</td>
                  <td>
                    <button disabled={busy} onClick={() => revoke(s)}>
                      {t("revokeSession")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
