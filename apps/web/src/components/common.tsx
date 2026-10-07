"use client";
import Link from "next/link";
import { Document } from "@/lib/types";
import { useI18n } from "./provider";
export function ErrorBox({ code }: { code: string }) {
  const { t } = useI18n();
  return code ? (
    <p role="alert" className="error">
      {t(code)}
    </p>
  ) : null;
}
export function Badge({ status }: { status: string }) {
  const { t } = useI18n();
  return (
    <span className={`badge status-${status.toLowerCase()}`}>{t(status)}</span>
  );
}
export function DocumentTable({ items }: { items: Document[] }) {
  const { t, lang } = useI18n();
  return items.length ? (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t("number")}</th>
            <th>{t("title")}</th>
            <th>{t("status")}</th>
            <th>{t("updated")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id}>
              <td>
                <Link className="mono" href={`/documents/${d.id}`}>
                  {d.number}
                </Link>
              </td>
              <td>
                <Link href={`/documents/${d.id}`}>{d.title}</Link>
              </td>
              <td>
                <Badge status={d.status} />
              </td>
              <td>{new Date(d.updated_at).toLocaleDateString(lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <div className="empty">{t("empty")}</div>
  );
}
