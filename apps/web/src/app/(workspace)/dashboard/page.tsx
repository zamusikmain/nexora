"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Dashboard } from "@/lib/types";
import { useI18n } from "@/components/provider";
import { Badge, DocumentTable, ErrorBox } from "@/components/common";
export default function Page() {
  const { t } = useI18n();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<Dashboard>("/dashboard")
      .then(setData)
      .catch((e) => setError(e instanceof ApiError ? e.code : "error"));
  }, []);
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">NEXORA / {t("workspace")}</p>
          <h1>{t("dashboard")}</h1>
        </div>
        <Link className="primary button" href="/documents/new">
          + {t("newDocument")}
        </Link>
      </div>
      <ErrorBox code={error} />
      {!data && !error ? (
        <p>{t("loading")}</p>
      ) : (
        data && (
          <>
            <div className="stats">
              {[
                ["myDocuments", data.my_documents],
                [
                  "visibleDocuments",
                  Object.values(data.by_status).reduce((a, b) => a + b, 0),
                ],
                [
                  "inProgress",
                  ["SUBMITTED", "IN_REVIEW", "IN_APPROVAL"].reduce(
                    (n, key) => n + (data.by_status[key] || 0),
                    0,
                  ),
                ],
                ["revision", data.by_status.REVISION_REQUIRED || 0],
              ].map(([key, value]) => (
                <div className="stat" key={key}>
                  <span>{t(String(key))}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <section className="panel">
              <h2>{t("recent")}</h2>
              <DocumentTable items={data.recent} />
            </section>
            <section className="panel">
              <h2>{t("byStatus")}</h2>
              <div className="status-counts">
                {Object.entries(data.by_status).map(([key, value]) => (
                  <div key={key}>
                    <Badge status={key} />
                    <strong>{value}</strong>
                  </div>
                ))}
                {!Object.keys(data.by_status).length && <p>{t("empty")}</p>}
              </div>
            </section>
          </>
        )
      )}
    </>
  );
}
