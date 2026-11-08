// Per-request nonce: Next.js reads it from the request CSP header and tags its own scripts,
// so no inline script runs without it. Styles keep 'unsafe-inline' for React style attributes.
export function contentSecurityPolicy(nonce: string, development: boolean) {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    // NCALayer (ЭЦП) listens only on the signer's own machine; nothing else leaves the origin.
    "connect-src 'self' wss://127.0.0.1:13579",
    "frame-ancestors 'none'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join("; ");
}

export function createNonce() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return btoa(String.fromCharCode(...bytes));
}
