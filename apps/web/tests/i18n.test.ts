import { test } from "node:test";
import assert from "node:assert/strict";
import { ru, en } from "../src/lib/i18n.ts";
import { kk } from "../src/lib/i18n-kk.ts";
test("RU, KK and EN have matching complete dictionaries", () => {
  assert.deepEqual(Object.keys(ru).sort(), Object.keys(en).sort());
  assert.deepEqual(Object.keys(kk).sort(), Object.keys(ru).sort());
  for (const value of [...Object.values(ru), ...Object.values(kk), ...Object.values(en)])
    assert.ok(value.trim());
});
test("Kazakh texts are actually Kazakh, not copied Russian", () => {
  // Words spelled identically in both languages, and the language names themselves.
  const shared = ["languageRu", "languageKk", "code", "audit", "bytes", "accessAction_card", "accessAction_file"];
  const same = Object.keys(ru).filter((key) => /[а-яё]/i.test(ru[key]) && kk[key] === ru[key]);
  assert.deepEqual(same.sort(), shared.sort());
});
test("Every implemented status and audit event is translated", () => {
  for (const key of [
    "DRAFT",
    "SUBMITTED",
    "CANCELLED",
    "ARCHIVED",
    "DOCUMENT_CREATED",
    "DOCUMENT_UPDATED",
    "DOCUMENT_SUBMITTED",
    "DOCUMENT_ARCHIVED",
    "DOCUMENT_CANCELLED",
    "VERSION_CREATED",
    "FILE_UPLOADED",
    "FILE_DOWNLOADED",
    "COMMENT_ADDED",
    "USER_LOGIN",
    "USER_LOGIN_FAILED",
    "USER_LOGOUT",
    "USER_UPDATED",
  ]) {
    assert.ok(ru[key]);
    assert.ok(en[key]);
  }
});

test("Literal translation calls and audit events have dictionary entries", async () => {
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  async function files(dir: string): Promise<string[]> {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    const result: string[] = [];
    for (const e of entries) {
      const file = path.join(dir, e.name);
      if (e.isDirectory()) result.push(...(await files(file)));
      else if (/\.(tsx?|py)$/.test(file)) result.push(file);
    }
    return result;
  }
  for (const file of await files("src")) {
    const source = await fs.readFile(file, "utf8");
    for (const match of source.matchAll(/\bt\(["']([^"']+)["']\)/g))
      assert.ok(ru[match[1]], `${file}: missing ${match[1]}`);
  }
  for (const file of await files("../api/app")) {
    const source = await fs.readFile(file, "utf8");
    for (const match of source.matchAll(/(?:"|')([A-Z]+_[A-Z_]+)(?:"|')/g)) {
      const key = match[1];
      if (
        /^(DOCUMENT_|VERSION_|VERSIONS_|FOLDER_)/.test(key) &&
        !key.includes("REVISION") &&
        key !== "DOCUMENT_NUMBER_SEQ"
      )
        assert.ok(ru[key], `${file}: untranslated event ${key}`);
    }
  }
});
test("JSX contains no prose text outside localization", async () => {
  const ts = await import("typescript");
  const fs = await import("node:fs/promises");
  const path = await import("node:path");
  async function inspect(dir: string): Promise<void> {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) await inspect(file);
      else if (file.endsWith(".tsx")) {
        const source = ts.createSourceFile(
          file,
          await fs.readFile(file, "utf8"),
          ts.ScriptTarget.Latest,
          true,
          ts.ScriptKind.TSX,
        );
        function visit(node: import("typescript").Node) {
          if (ts.isJsxText(node)) {
            const text = node.getText(source).trim();
            assert.ok(
              !/[A-Za-zА-Яа-я]{3}/.test(text) || /^NEXORA\s*\/?$/.test(text),
              `${file}: hardcoded JSX ${text}`,
            );
          }
          ts.forEachChild(node, visit);
        }
        visit(source);
      }
    }
  }
  await inspect("src");
});
