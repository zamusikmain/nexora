import { expect, test as base, type Page } from "@playwright/test";

export const password = process.env.E2E_PASSWORD || "";

export const test = base.extend<{ cspViolations: string[] }>({
  // Every test fails on a Content-Security-Policy violation in the browser console.
  cspViolations: [
    async ({ page }, use) => {
      const violations: string[] = [];
      page.on("console", (message) => {
        if (/Content.Security.Policy/i.test(message.text())) violations.push(message.text());
      });
      await use(violations);
      expect(violations, "CSP violations").toEqual([]);
    },
    { auto: true },
  ],
});

export async function preferEnglish(page: Page) {
  await page.addInitScript(() => localStorage.setItem("nexora-language", "en"));
}

export async function signIn(page: Page, email: string) {
  test.skip(!password, "Set E2E_PASSWORD to the stack's DEMO_PASSWORD");
  await preferEnglish(page);
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

// The app's ErrorBox; Next.js also renders an empty role="alert" route announcer.
export const errorBox = (page: Page) => page.locator("p.error[role=alert]");

export { expect };
