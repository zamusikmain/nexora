import assert from "node:assert/strict";
import { test } from "node:test";
import { api, ApiError, setCsrf } from "../src/lib/api.ts";

// The server issues signed keys; the stub hands out distinct synthetic ones.
let issued = 0;
function issueKey(url: unknown) {
  if (String(url) !== "/api/v1/operation-keys") return null;
  return new Response(JSON.stringify({ key: `nx1.synthetic-${++issued}.sig` }), { status: 201 });
}

test("unknown outcomes keep the same key; successful new actions receive new keys", async () => {
  const original = globalThis.fetch;
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } });
  const seen: string[] = [];
  let attempt = 0;
  let keyRequests = 0;
  globalThis.fetch = async (url, options) => {
    const key = issueKey(url);
    if (key) { keyRequests++; return key; }
    seen.push(new Headers(options?.headers).get("Idempotency-Key") || "");
    if (++attempt === 1) throw Error("Synthetic lost response");
    if (attempt === 2) return new Response(JSON.stringify({ error: "server_error" }), { status: 503 });
    return new Response(JSON.stringify({ id: "same-document" }), { status: 201 });
  };
  try {
    setCsrf("synthetic-csrf", "synthetic-owner");
    const options = { method: "POST", body: JSON.stringify({ title: "Test" }) };
    await assert.rejects(api("/documents", options), /Synthetic lost response/);
    setCsrf("new-session-csrf", "synthetic-owner");
    await assert.rejects(api("/documents", options), ApiError);
    assert.deepEqual(await api("/documents", options), { id: "same-document" });
    assert.equal(seen[0], seen[1]); assert.equal(seen[1], seen[2]);
    assert.match(seen[0], /^nx1\./);
    assert.equal(keyRequests, 1, "retries reuse the stored key instead of asking for a new one");
    await api("/documents", options);
    assert.notEqual(seen[2], seen[3]);
    assert.equal(keyRequests, 2);
    assert.equal(values.size, 0);
    await api("/documents", { ...options, headers: { "Idempotency-Key": "explicit-test-key" } });
    assert.equal(seen[4], "explicit-test-key");
    const workflowKeys: string[] = [];
    globalThis.fetch = async (url, request) => {
      const key = issueKey(url);
      if (key) return key;
      const body = JSON.parse(String(request?.body));
      assert.equal(body.idempotency_key, new Headers(request?.headers).get("Idempotency-Key"));
      workflowKeys.push(body.idempotency_key);
      if (workflowKeys.length === 1) throw Error("Synthetic workflow lost response");
      return new Response("{}", { status: 200 });
    };
    const decision = { method: "POST", body: JSON.stringify({ action: "approve", comment: "Checked" }) };
    await assert.rejects(api("/workflows/test-instance/decisions", decision));
    await api("/workflows/test-instance/decisions", decision);
    assert.equal(workflowKeys[0], workflowKeys[1]);
  } finally { globalThis.fetch = original; setCsrf(""); }
});

test("an expired key is surfaced, not silently replaced, and the next action gets a fresh key", async () => {
  const original = globalThis.fetch;
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "sessionStorage", { configurable: true, value: {
    getItem: (key: string) => values.get(key) || null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  } });
  const sent: string[] = [];
  globalThis.fetch = async (url, options) => {
    const key = issueKey(url);
    if (key) return key;
    sent.push(new Headers(options?.headers).get("Idempotency-Key") || "");
    return sent.length === 1
      ? new Response(JSON.stringify({ error: "operation_expired" }), { status: 409 })
      : new Response(JSON.stringify({ id: "new" }), { status: 201 });
  };
  try {
    setCsrf("synthetic-csrf", "synthetic-owner");
    const options = { method: "POST", body: JSON.stringify({ title: "Expired" }) };
    await assert.rejects(api("/documents", options), (e: unknown) => e instanceof ApiError && e.code === "operation_expired");
    assert.equal(sent.length, 1, "no automatic resend with a new key");
    await api("/documents", options);
    assert.notEqual(sent[0], sent[1]);
  } finally { globalThis.fetch = original; setCsrf(""); }
});

test("a failed key request stops the action before anything is sent", async () => {
  const original = globalThis.fetch;
  let actionSent = false;
  globalThis.fetch = async (url) => {
    if (String(url) === "/api/v1/operation-keys") return new Response(JSON.stringify({ error: "csrf_failed" }), { status: 403 });
    actionSent = true;
    return new Response("{}", { status: 201 });
  };
  try {
    setCsrf("synthetic-csrf", "synthetic-owner");
    await assert.rejects(api("/documents", { method: "POST", body: "{}" }),
      (e: unknown) => e instanceof ApiError && e.code === "csrf_failed");
    assert.equal(actionSent, false);
  } finally { globalThis.fetch = original; setCsrf(""); }
});
