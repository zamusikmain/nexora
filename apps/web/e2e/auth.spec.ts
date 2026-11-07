import { errorBox, expect, password, signIn, test, preferEnglish } from "./fixtures";

test("Russian is the default and the language choice survives a reload", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Вход в рабочее пространство" })).toBeVisible();
  await page.getByRole("combobox").selectOption("en");
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in to your workspace" })).toBeVisible();
});

test("wrong password is rejected without revealing which field was wrong", async ({ page }) => {
  await preferEnglish(page);
  await page.goto("/login");
  await page.getByLabel("Email").fill("user@nexora.local");
  await page.getByLabel("Password").fill("definitely-not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(errorBox(page)).toHaveText("Invalid credentials");
  await expect(page).toHaveURL(/\/login$/);
});

test("protected pages redirect to login after sign-out", async ({ page }) => {
  test.skip(!password, "Set E2E_PASSWORD to the stack's DEMO_PASSWORD");
  await signIn(page, "user@nexora.local");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/documents");
  await expect(page).toHaveURL(/\/login$/);
});
