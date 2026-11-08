import assert from "node:assert/strict";
import { test } from "node:test";
import { NCALAYER_URL, signRequest, signWithNcaLayer, toBase64 } from "../src/lib/ncalayer.ts";

type Handler = ((event: never) => void) | null;

// Minimal NCALayer double: records what the page sends and replays scripted answers.
function fakeLayer(script: (socket: FakeSocket) => void) {
  const sockets: FakeSocket[] = [];
  const open = (url: string) => {
    const socket = new FakeSocket(url, script);
    sockets.push(socket);
    return socket;
  };
  return { open, sockets };
}

class FakeSocket {
  sent: unknown[] = [];
  closed = false;
  onopen: Handler = null;
  onmessage: Handler = null;
  onerror: Handler = null;
  onclose: Handler = null;
  url: string;
  constructor(url: string, script: (socket: FakeSocket) => void) {
    this.url = url;
    queueMicrotask(() => script(this));
  }
  send(data: string) {
    this.sent.push(JSON.parse(data));
  }
  close() {
    this.closed = true;
  }
  emit(name: "onopen" | "onmessage" | "onerror" | "onclose", data?: unknown) {
    const handler = this[name] as ((event: unknown) => void) | null;
    handler?.(data === undefined ? {} : { data: JSON.stringify(data) });
  }
}

test("signs the exact base64 data, skipping NCALayer's version greeting", async () => {
  const layer = fakeLayer((s) => {
    s.emit("onopen");
    s.emit("onmessage", { result: { version: "1.4" } });
    s.emit("onmessage", { status: true, body: { result: ["CMS=="] } });
  });
  assert.equal(await signWithNcaLayer("AAEC", "kk", layer.open as never), "CMS==");
  const socket = layer.sockets[0];
  assert.equal(socket.url, NCALAYER_URL);
  assert.deepEqual(socket.sent, [signRequest("AAEC", "kk")]);
  assert.equal(socket.closed, true);
});

test("detached CMS with signing-certificate filter and supported locales", () => {
  const request = signRequest("AA==", "de");
  assert.equal(request.module, "kz.gov.pki.knca.basics");
  assert.equal(request.args.format, "cms");
  assert.equal(request.args.signingParams.encapsulate, false);
  assert.deepEqual(request.args.signerParams.extKeyUsageOids, ["1.3.6.1.5.5.7.3.4"]);
  assert.equal(request.args.locale, "ru");
});

test("cancel, failure and a missing NCALayer map to distinct errors", async () => {
  const outcomes = [
    [(s: FakeSocket) => { s.emit("onopen"); s.emit("onmessage", { status: true, body: {} }); }, "ncalayer_cancelled"],
    [(s: FakeSocket) => { s.emit("onopen"); s.emit("onmessage", { status: false, code: "500" }); }, "ncalayer_failed"],
    [(s: FakeSocket) => { s.emit("onerror"); s.emit("onclose"); }, "ncalayer_unavailable"],
  ] as const;
  for (const [script, code] of outcomes) {
    await assert.rejects(signWithNcaLayer("AA==", "ru", fakeLayer(script).open as never), { code });
  }
});

test("a socket that never connects is reported as NCALayer unavailable", async () => {
  const silent = fakeLayer(() => undefined);
  await assert.rejects(signWithNcaLayer("AA==", "ru", silent.open as never, 20), { code: "ncalayer_unavailable" });
  assert.equal(silent.sockets[0].closed, true);
});

test("base64 conversion handles files larger than one chunk", () => {
  const bytes = new Uint8Array(100_000).map((_, i) => i % 256);
  assert.equal(toBase64(bytes), Buffer.from(bytes).toString("base64"));
});
