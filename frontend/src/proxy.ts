import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);

function isLoopbackPeer(value: string | null): boolean {
  // frontend/server.js overwrites this header from req.socket.remoteAddress
  // before Next sees the request, so it is never caller-controlled here.
  const peer = (value || "").split(",", 1)[0].trim().replace(/^\[|\]$/g, "");
  return LOOPBACK.has(peer);
}

// Next 16 calls Middleware "Proxy". Rewrites stream backend responses; this
// layer only supplies the security marker that a rewrite itself cannot add.
export function proxy(request: NextRequest) {
  if (process.env.TT_SINGLE_PORT_PROXY !== "1") {
    return new NextResponse(null, { status: 404 });
  }
  const headers = new Headers(request.headers);
  // A caller can only ever lose trust by sending this header, never gain it.
  // Remove it first so the decision below is based solely on the real peer.
  headers.delete("x-tt-proxied");
  if (!isLoopbackPeer(headers.get("x-forwarded-for"))) {
    headers.set("x-tt-proxied", "1");
  }
  // Use a rewrite rather than a route handler: Next streams the backend
  // response. Supplying the request headers here is required because external
  // rewrites otherwise omit Authorization on the upstream hop.
  const target = (process.env.TT_PROXY_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
  const suffix = request.nextUrl.pathname.slice("/_tt-api".length) || "/";
  const destination = new URL(`${target}${suffix}${request.nextUrl.search}`);
  return NextResponse.rewrite(destination, { request: { headers } });
}

export const config = { matcher: ["/_tt-api/:path*"] };