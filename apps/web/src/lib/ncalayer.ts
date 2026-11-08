// Client for NCALayer, the НУЦ РК desktop application that holds the signer's ЭЦП keys.
// It listens only on the user's own machine (wss://127.0.0.1:13579); the key never reaches
// NEXORA. We send the exact file bytes and receive a detached CMS signature.

export const NCALAYER_URL = "wss://127.0.0.1:13579";

export class NcaLayerError extends Error {
  // ncalayer_unavailable | ncalayer_cancelled | ncalayer_failed
  code: string;
  constructor(code: string) {
    super(code);
    this.code = code;
  }
}

type Socket = Pick<WebSocket, "send" | "close"> & {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
};

export function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000)
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function signRequest(data: string, locale: string) {
  return {
    module: "kz.gov.pki.knca.basics",
    method: "sign",
    args: {
      allowedStorages: null,
      format: "cms",
      data,
      signingParams: { decode: true, encapsulate: false, digested: false, tsaProfile: {} },
      // 1.3.6.1.5.5.7.3.4: signing (not authentication) certificates only.
      signerParams: { extKeyUsageOids: ["1.3.6.1.5.5.7.3.4"], chain: [] },
      locale: locale === "kk" ? "kk" : locale === "en" ? "en" : "ru",
    },
  };
}

export function signWithNcaLayer(
  data: string,
  locale: string,
  open: (url: string) => Socket = (url) => new WebSocket(url),
  connectTimeoutMs = 10_000,
): Promise<string> {
  return new Promise((resolve, reject) => {
    let socket: Socket;
    try {
      socket = open(NCALAYER_URL);
    } catch {
      reject(new NcaLayerError("ncalayer_unavailable"));
      return;
    }
    let opened = false;
    let settled = false;
    // A closed local port can take seconds to refuse; don't leave the user waiting on nothing.
    // Once connected there is no limit: the user is choosing a key and typing a password.
    const timer = setTimeout(() => {
      if (!opened) finish(new NcaLayerError("ncalayer_unavailable"));
    }, connectTimeoutMs);
    const finish = (error: NcaLayerError | null, cms?: string) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { socket.close(); } catch { /* already closed */ }
      if (error) reject(error);
      else resolve(cms!);
    };
    socket.onopen = () => {
      if (settled) return; // timed out already: never pop a signing dialog the page no longer awaits
      opened = true;
      socket.send(JSON.stringify(signRequest(data, locale)));
    };
    socket.onmessage = (event) => {
      let message: { status?: boolean; code?: string; body?: { result?: unknown } };
      try {
        message = JSON.parse(String(event.data));
      } catch {
        return;
      }
      // NCALayer greets with its version before answering; only a status message is the answer.
      if (typeof message.status !== "boolean") return;
      if (!message.status) {
        finish(new NcaLayerError("ncalayer_failed"));
        return;
      }
      const result = message.body?.result;
      const cms = Array.isArray(result) ? result[0] : result;
      if (typeof cms === "string" && cms.length > 0) finish(null, cms);
      else finish(new NcaLayerError("ncalayer_cancelled")); // empty body: the user closed the dialog
    };
    socket.onerror = () => finish(new NcaLayerError(opened ? "ncalayer_failed" : "ncalayer_unavailable"));
    socket.onclose = () => finish(new NcaLayerError(opened ? "ncalayer_failed" : "ncalayer_unavailable"));
  });
}
