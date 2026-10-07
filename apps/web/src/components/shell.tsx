"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useContext, useEffect, useState } from "react";
import { api, setCsrf } from "@/lib/api";
import { User } from "@/lib/types";
import { Language, useI18n } from "./provider";
const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);
export function Shell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ user: User; csrf_token: string }>("/auth/me")
      .then((data) => {
        setCsrf(data.csrf_token);
        setUser(data.user);
      })
      .catch(() => setError("unauthorized"));
  }, []);
  useEffect(() => {
    const expired = () => router.replace("/login");
    window.addEventListener("nexora-unauthorized", expired);
    return () => window.removeEventListener("nexora-unauthorized", expired);
  }, [router]);
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setCsrf("");
      router.replace("/login");
    } catch {
      setError("error");
    }
  }
  const links = [
    ["/dashboard", "dashboard"],
    ["/documents", "documents"],
    ...(user?.role === "ADMIN"
      ? [
          ["/admin/users", "users"],
          ["/admin/document-types", "documentTypes"],
          ["/admin/audit", "audit"],
        ]
      : []),
  ];
  return (
    <UserContext.Provider value={user}>
      <div className="workspace">
        <aside>
          <Link className="brand" href="/dashboard">
            <span className="logo">N</span>NEXORA
          </Link>
          <p className="caption">{t("tagline")}</p>
          <div className="nav-label">{t("workspace")}</div>
          <nav>
            {links.map(([href, label]) => (
              <Link
                className={path.startsWith(href) ? "active" : ""}
                key={href}
                href={href}
              >
                {t(label)}
              </Link>
            ))}
          </nav>
          <div className="sidebar-foot">
            <span className="dot" /> {t("access")}
          </div>
        </aside>
        <div className="main">
          <header>
            <span>{t("workspace")}</span>
            <div className="header-actions">
              <Language />
              {user && (
                <span className="user-name">
                  {user.display_name} <small>{t(user.role)}</small>
                </span>
              )}
              <button className="quiet" onClick={logout}>
                {t("logout")}
              </button>
            </div>
          </header>
          <main>
            {error ? (
              <p role="alert" className="error">
                {t(error)}
              </p>
            ) : !user ? (
              <p role="status">{t("loading")}</p>
            ) : (
              children
            )}
          </main>
        </div>
      </div>
    </UserContext.Provider>
  );
}
