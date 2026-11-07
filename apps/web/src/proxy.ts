import { NextResponse, type NextRequest } from "next/server";

import { contentSecurityPolicy, createNonce } from "@/lib/csp";

export function proxy(request: NextRequest) {
  const nonce = createNonce();
  const policy = contentSecurityPolicy(nonce, process.env.NODE_ENV === "development");
  // Overwrite any client-supplied values: Next.js takes the nonce from the request CSP header.
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api/|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
