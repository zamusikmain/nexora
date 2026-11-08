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

  // ЭЦП: the local NCALayer socket is fully mocked, so a real NCALayer on the machine is never contacted.
  const signaturesUrl = `/api/v1/documents/${documentUrl.split("/").pop()}/signatures`;
  let layerRunning = false;
  const requests: { module: string; args: { data: string; format: string } }[] = [];
  await page.routeWebSocket("wss://127.0.0.1:13579", (ws) => {
    if (!layerRunning) {
      ws.close();
      return;
    }
    ws.send(JSON.stringify({ result: { version: "1.4" } }));
    ws.onMessage((message) => {
      requests.push(JSON.parse(String(message)));
      ws.send(JSON.stringify({ status: true, body: { result: [Buffer.from("e2e-cms-signature").toString("base64")] } }));
    });
  });
  await version.getByRole("button", { name: "Sign with EDS" }).click();
  await expect(errorBox(page)).toHaveText("NCALayer is not running. Start NCALayer and try again.");
  expect(await (await page.request.get(signaturesUrl)).json()).toEqual([]);

  layerRunning = true;
  await version.getByRole("button", { name: "Sign with EDS" }).click();
  // Development has no verifier: the signature is stored and honestly labelled as not verified.
  await expect(version.locator(".signature.unverified")).toContainText("Signature stored, not verified by the server:");
  expect(requests).toHaveLength(1);
  expect(requests[0].module).toBe("kz.gov.pki.knca.basics");
  expect(requests[0].args.format).toBe("cms");
  expect(Buffer.from(requests[0].args.data, "base64").toString()).toBe(content); // the exact stored bytes
  await expect(version.getByRole("button", { name: "Sign with EDS" })).toHaveCount(0); // one signature per user
  const cms = await page.request.get(`${signaturesUrl}/${(await (await page.request.get(signaturesUrl)).json())[0].id}/cms`);
  expect(await cms.text()).toBe("e2e-cms-signature");

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
