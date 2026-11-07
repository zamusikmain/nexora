import type { Metadata } from "next";
import { connection } from "next/server";
import { Provider } from "@/components/provider";
import "./globals.css";
export const metadata: Metadata = { title: "NEXORA", description: "NEXORA" };
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // CSP nonces exist only per request: render dynamically so Next.js can tag its scripts.
  await connection();
  return (
    <html lang="ru">
      <body>
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
