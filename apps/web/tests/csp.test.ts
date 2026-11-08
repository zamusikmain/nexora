import assert from "node:assert/strict";
import { test } from "node:test";
import { contentSecurityPolicy, createNonce } from "../src/lib/csp.ts";

test("scripts require the per-request nonce; inline scripts and eval are not allowed in production", () => {
  const policy = contentSecurityPolicy("abc123==", false);
  const script = policy.split("; ").find((part) => part.startsWith("script-src "));
  assert.equal(script, "script-src 'self' 'nonce-abc123==' 'strict-dynamic'");
  assert.ok(policy.includes("frame-ancestors 'none'"));
  assert.ok(policy.includes("object-src 'none'"));
  assert.ok(contentSecurityPolicy("n", true).includes("'unsafe-eval'"));
  // Only same-origin requests plus the local NCALayer socket for ЭЦП.
  assert.ok(policy.includes("connect-src 'self' wss://127.0.0.1:13579;"));
});

test("nonces are unpredictable base64 values", () => {
  const first = createNonce();
  assert.match(first, /^[A-Za-z0-9+/]{22}==$/);
  assert.notEqual(first, createNonce());
});
