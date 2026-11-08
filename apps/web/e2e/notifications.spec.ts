import { randomUUID } from "node:crypto";
import type { Page } from "@playwright/test";
import { expect, signIn, test } from "./fixtures";

// Setup goes through the same HTTP API as the UI, with the signed-in session, CSRF and Origin.
async function post(page: Page, path: string, data: Record<string, unknown>) {
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const response = await page.request.post(`/api/v1${path}`, {
    data,
    headers: {
      "x-csrf-token": me.csrf_token,
      origin: new URL(page.url()).origin,
      "Idempotency-Key": randomUUID(),
    },
  });
  expect(response.status(), await response.text()).toBe(201);
  return response.json();
}

test("a started workflow notifies the reviewer, who opens the task and reads it", async ({ page, browser }) => {
  const title = `E2E notification ${Date.now()}`;
  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await signIn(admin, "admin@nexora.local");
  const template = await post(admin, "/workflow-templates", {
    code: `E2E_${Date.now()}`,
    name_ru: "E2E",
    name_en: "E2E",
    stages: [{ name_ru: "Проверка", name_en: "Review", selector: "role", targets: ["REVIEWER"] }],
  });
  await adminContext.close();

  await signIn(page, "user@nexora.local");
  await page.goto("/documents/new");
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/documents\/[0-9a-f-]{36}$/);
  const documentId = page.url().split("/").pop()!;
  await page.getByLabel(/^File/).setInputFiles({ name: "n.txt", mimeType: "text/plain", buffer: Buffer.from("note\n") });
  await page.getByRole("button", { name: "Upload version" }).click();
  await expect(page.locator(".version", { hasText: "n.txt" })).toContainText("v1");
  const document = await (await page.request.get(`/api/v1/documents/${documentId}`)).json();
  await post(page, `/documents/${documentId}/workflows`, {
    template_id: template.id,
    expected_revision: document.revision,
    idempotency_key: randomUUID(),
  });

  const reviewerContext = await browser.newContext();
  const reviewer = await reviewerContext.newPage();
  await signIn(reviewer, "reviewer@nexora.local");
  const navLink = reviewer.getByRole("link", { name: /^Notifications/ });
  await expect(navLink.locator(".count")).toBeVisible();
  await navLink.click();
  const item = reviewer.locator(".notifications li.unread", { hasText: title });
  await expect(item).toContainText("You have a new approval task");
  await expect(item).toContainText("User Demo");

  await item.getByRole("button", { name: "Mark as read" }).click();
  await expect(reviewer.locator(".notifications li", { hasText: title })).not.toHaveClass(/unread/);
  await reviewer.locator(".notifications li", { hasText: title }).getByRole("link", { name: "Open" }).click();
  await expect(reviewer).toHaveURL(/\/approvals\/[0-9a-f-]{36}\/review$/);
  await reviewerContext.close();
});
