import { test } from "node:test";
import assert from "node:assert/strict";
import { ru, en } from "../src/lib/i18n.ts";
test("RU and EN have matching complete dictionaries", () => {
  assert.deepEqual(Object.keys(ru).sort(), Object.keys(en).sort());
  for (const value of [...Object.values(ru), ...Object.values(en)])
    assert.ok(value.trim());
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
