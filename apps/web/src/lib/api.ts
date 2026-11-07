let csrf = "";
let actor = "";
const pending = new Map<string, string>();

async function operationKey(path: string, method: string, body: BodyInit | null | undefined) {
  const parts: unknown[] = [actor, path, method];
  if (body instanceof FormData) {
    for (const [name, value] of body.entries()) {
      parts.push(value instanceof File ? [name, value.name, value.type, value.size,
        Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", await value.arrayBuffer())))] : [name, value]);
    }
  } else parts.push(body || "");
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(parts)));
  const fingerprint = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  const storageKey = `nexora-operation:${fingerprint}`;
  let key = pending.get(storageKey);
  try { key ||= sessionStorage.getItem(storageKey) || undefined; } catch { /* Storage may be disabled. */ }
  // The server signs and dates the key; it is stored BEFORE the action is sent, so a lost
  // response is retried with the same key. An expired key gets 409 operation_expired.
  key ||= await issueOperationKey(); pending.set(storageKey, key);
  try { sessionStorage.setItem(storageKey, key); } catch { /* Memory preserves same-tab retries. */ }
  return { key, storageKey };
}

async function issueOperationKey(): Promise<string> {
  const response = await fetch("/api/v1/operation-keys", {
    method: "POST", headers: { "X-CSRF-Token": csrf }, credentials: "same-origin", cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || typeof data.key !== "string") {
    if (response.status === 401 && typeof window !== "undefined") window.dispatchEvent(new Event("nexora-unauthorized"));
    throw new ApiError(typeof data.error === "string" ? data.error : "server_error", response.status);
  }
  return data.key;
}
export function setCsrf(value: string, actorId = "") {
  csrf = value;
  actor = actorId;
}
export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method || "GET";
  const headers = new Headers(options.headers);
  const operation = !path.startsWith("/auth/") && !["GET", "HEAD"].includes(method) && !headers.has("Idempotency-Key")
    ? await operationKey(path, method, options.body) : null;
  if (operation) headers.set("Idempotency-Key", operation.key);
  const workflow = /^\/(documents\/[^/]+\/workflows|workflows\/[^/]+\/decisions)$/.test(path);
  const workflowBody = workflow && method === "POST" && typeof options.body === "string"
    ? JSON.parse(options.body) as Record<string, unknown> : null;
  const body = workflowBody && !workflowBody.idempotency_key
    ? JSON.stringify({ ...workflowBody, idempotency_key: headers.get("Idempotency-Key") }) : options.body;
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method)) headers.set("X-CSRF-Token", csrf);
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    body,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  // Unknown network/5xx outcomes retain the same key across retries and reloads.
  if (operation && response.status < 500) {
    pending.delete(operation.storageKey);
    try { sessionStorage.removeItem(operation.storageKey); } catch { /* Storage may be disabled. */ }
  }
  if (!response.ok) {
    const data = await response.json().catch(() => ({ error: "server_error" }));
    if (
      response.status === 401 &&
      path !== "/auth/login" &&
      typeof window !== "undefined"
    )
      window.dispatchEvent(new Event("nexora-unauthorized"));
    throw new ApiError(
      typeof data.error === "string" ? data.error : "validation_error",
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
