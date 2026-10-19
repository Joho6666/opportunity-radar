import { NextRequest, NextResponse } from "next/server";
import { createLocalSession, LOCAL_SESSION_COOKIE, LOCAL_SESSION_TTL_SECONDS, verifyLocalSession } from "@/lib/server/local-session";
import { hasUntrustedNextHeaders, isAllowedLocalSessionBootstrap } from "@/lib/local-request-guards";

export const runtime = "nodejs";

function allowedRead(request: NextRequest): boolean {
  const origin = process.env.LOCAL_UI_ORIGIN ?? "http://localhost:3004";
  const url = new URL(origin);
  return request.headers.get("host") === url.host
    && !hasUntrustedNextHeaders(request.headers, url.host, request.nextUrl.protocol)
    && request.headers.get("sec-fetch-site") !== "cross-site"
    && (!request.headers.get("origin") || request.headers.get("origin") === origin);
}

export async function GET(request: NextRequest) {
  if (process.env.APP_ENV !== "local" || !allowedRead(request)) {
    return NextResponse.json({ authenticated: false }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const session = verifyLocalSession(request.cookies.get(LOCAL_SESSION_COOKIE)?.value);
  return NextResponse.json(session ? { authenticated: true, csrf_token: session.csrfToken } : { authenticated: false }, { headers: { "Cache-Control": "no-store", Vary: "Cookie" } });
}

export async function POST(request: NextRequest) {
  const origin = process.env.LOCAL_UI_ORIGIN ?? "http://localhost:3004";
  if (process.env.APP_ENV !== "local" || !isAllowedLocalSessionBootstrap(request.headers, origin, request.nextUrl.protocol)) {
    return NextResponse.json({ error: "本地会话初始化仅允许本机同源请求。" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }

  // Reuse a still-valid session so retries and concurrent bootstrap requests
  // from the same browser do not invalidate the CSRF token already in flight.
  const existing = verifyLocalSession(request.cookies.get(LOCAL_SESSION_COOKIE)?.value);
  const session = existing ? null : createLocalSession();
  const csrfToken = existing?.csrfToken ?? session!.csrfToken;
  const response = NextResponse.json({ authenticated: true, csrf_token: csrfToken }, { headers: { "Cache-Control": "no-store", Vary: "Cookie" } });
  if (session) response.cookies.set(LOCAL_SESSION_COOKIE, session.value, { httpOnly: true, sameSite: "strict", path: "/", maxAge: LOCAL_SESSION_TTL_SECONDS });
  return response;
}
