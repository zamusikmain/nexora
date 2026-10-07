"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, setCsrf } from "@/lib/api";
import { Language, useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
export default function Login() {
  const { t } = useI18n();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const data = await api<{ csrf_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      setCsrf(data.csrf_token);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.code : "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-language">
        <Language />
      </div>
      <div className="login-card">
        <div className="brand">
          <span className="logo">N</span>NEXORA
        </div>
        <p className="caption">{t("tagline")}</p>
        <h1>{t("welcome")}</h1>
        <p>{t("loginHint")}</p>
        <form onSubmit={submit}>
          <label>
            {t("email")}
            <input
              name="email"
              type="email"
              autoComplete="username"
              required
              maxLength={254}
            />
          </label>
          <label>
            {t("password")}
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={256}
            />
          </label>
          <ErrorBox code={error} />
          <button disabled={busy} className="primary">
            {t(busy ? "loading" : "login")}
          </button>
        </form>
      </div>
    </div>
  );
}
