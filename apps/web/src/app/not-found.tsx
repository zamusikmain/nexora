"use client";
import Link from "next/link";
import { useI18n } from "@/components/provider";
export default function NotFound() {
  const { t } = useI18n();
  return (
    <main>
      <h1>{t("notFound")}</h1>
      <Link href="/dashboard">{t("dashboard")}</Link>
    </main>
  );
}
