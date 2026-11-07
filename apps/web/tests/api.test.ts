import assert from "node:assert/strict";
import { test } from "node:test";
import { api, ApiError, setCsrf } from "../src/lib/api.ts";

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
  globalThis.fetch = async (_url, options) => {
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
    assert.match(seen[0], /^[a-f0-9-]{36}$/);
    await api("/documents", options);
    assert.notEqual(seen[2], seen[3]);
    assert.equal(values.size, 0);
    await api("/documents", { ...options, headers: { "Idempotency-Key": "explicit-test-key" } });
    assert.equal(seen[4], "explicit-test-key");
    const workflowKeys: string[] = [];
    globalThis.fetch = async (_url, request) => {
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
