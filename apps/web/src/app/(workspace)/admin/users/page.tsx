"use client";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Catalog, User } from "@/lib/types";
import { useUser } from "@/components/shell";
import { useI18n } from "@/components/provider";
import { ErrorBox } from "@/components/common";
export default function Page() {
  const { t, lang } = useI18n();
  const me = useUser();
  const [users, setUsers] = useState<User[]>([]);
  const [departments, setDepartments] = useState<Catalog[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    Promise.all([api<User[]>("/users"), api<Catalog[]>("/departments")])
      .then(([a, b]) => {
        setUsers(a);
        setDepartments(b);
      })
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  async function save(e: React.FormEvent<HTMLFormElement>, user: User) {
    e.preventDefault();
    if (!window.confirm(t("confirm"))) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      const result = await api<User>(`/users/${user.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          role: f.get("role"),
          status: f.get("status"),
          department_id: f.get("department_id") || null,
        }),
      });
      setUsers((items) => items.map((u) => (u.id === result.id ? result : u)));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <h1>{t("users")}</h1>
      <ErrorBox code={error} />
      <section className="panel">
        {users.map((u) => (
          <form className="user-row" key={u.id} onSubmit={(e) => save(e, u)}>
            <div>
              <strong>{u.display_name}</strong>
              <small>{u.email}</small>
            </div>
            <label>
              {t("role")}
              <select
                name="role"
                defaultValue={u.role}
                disabled={u.id === me?.id}
              >
                {[
                  "USER",
                  "REVIEWER",
                  "APPROVER",
                  "LEGAL",
                  "MANAGER",
                  "ADMIN",
                ].map((r) => (
                  <option key={r} value={r}>
                    {t(r)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("userStatus")}
              <select
                name="status"
                defaultValue={u.status}
                disabled={u.id === me?.id}
              >
                {["ACTIVE", "BLOCKED", "DISABLED"].map((s) => (
                  <option key={s} value={s}>
                    {t(s)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("department")}
              <select
                name="department_id"
                defaultValue={u.department_id || ""}
                disabled={u.id === me?.id}
              >
                <option value="">—</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>
                    {lang === "ru" ? d.name_ru : d.name_en}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={busy || u.id === me?.id}>{t("save")}</button>
          </form>
        ))}
      </section>
    </>
  );
}
