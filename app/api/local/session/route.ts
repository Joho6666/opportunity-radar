import { NextRequest, NextResponse } from "next/server";
import { LOCAL_SESSION_COOKIE, verifyLocalSession } from "@/lib/server/local-session";
import { hasUntrustedNextHeaders } from "@/lib/local-request-guards";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const origin = process.env.LOCAL_UI_ORIGIN ?? "http://localhost:3004";
  const url = new URL(origin);
  if (request.headers.get("host") !== url.host || hasUntrustedNextHeaders(request.headers, url.host, request.nextUrl.protocol) || request.headers.get("sec-fetch-site") === "cross-site" || (request.headers.get("origin") && request.headers.get("origin") !== origin)) {
    return NextResponse.json({ authenticated: false }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const session = verifyLocalSession(request.cookies.get(LOCAL_SESSION_COOKIE)?.value);
  return NextResponse.json(session ? { authenticated: true, csrf_token: session.csrfToken } : { authenticated: false }, { headers: { "Cache-Control": "no-store", Vary: "Cookie" } });
}
