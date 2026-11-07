import { errorBox, expect, signIn, test } from "./fixtures";

test("owner creates a document, uploads a version and another department cannot open it", async ({ page, browser }) => {
  const title = `E2E document ${Date.now()}`;
  await signIn(page, "user@nexora.local");

  await page.goto("/documents/new");
  await page.getByLabel("Title").fill(title);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/documents\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
  await expect(page.getByText("Draft", { exact: true })).toBeVisible();
  const documentUrl = page.url();

  const content = `NEXORA e2e upload ${title}\n`;
  await page.getByLabel(/^File/).setInputFiles({ name: "e2e.txt", mimeType: "text/plain", buffer: Buffer.from(content) });
  await page.getByRole("button", { name: "Upload version" }).click();
  const version = page.locator(".version", { hasText: "e2e.txt" });
  await expect(version).toContainText("v1");
  await expect(version.getByText("Current", { exact: true })).toBeVisible();

  // The download is served privately to the owner with the exact uploaded bytes.
  const href = await version.getByRole("link", { name: "Download" }).getAttribute("href");
  const download = await page.request.get(href!);
  expect(download.status()).toBe(200);
  expect(await download.text()).toBe(content);

  await page.goto("/documents");
  await expect(page.getByRole("link", { name: title })).toBeVisible();

  // BOLA: a user of another department (separate cookies) gets the answer for a missing record.
  const strangerContext = await browser.newContext();
  const stranger = await strangerContext.newPage();
  await signIn(stranger, "other@nexora.local");
  await stranger.goto(documentUrl);
  await expect(errorBox(stranger)).toHaveText("Record unavailable");
  await expect(stranger.getByText(title)).toHaveCount(0);
  expect((await stranger.request.get(href!)).status()).toBe(404);
  await strangerContext.close();
});
