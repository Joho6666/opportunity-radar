import { NextRequest, NextResponse } from "next/server";
import { LOCAL_SESSION_COOKIE, safeEqualText, verifyLocalSession } from "@/lib/server/local-session";
import { hasUntrustedNextHeaders } from "@/lib/local-request-guards";

export const runtime = "nodejs";

function isLoopbackTarget(value: string): boolean {
  try {
    const target = new URL(value);
    const expectedPort = process.env.LOCAL_API_PORT ?? "8015";
    return target.protocol === "http:" && target.hostname === "127.0.0.1" && target.port === expectedPort && !target.username && !target.password;
  } catch { return false; }
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const origin = process.env.LOCAL_UI_ORIGIN ?? "http://localhost:3004";
  const originUrl = new URL(origin);
  const host = originUrl.host;
  if (process.env.APP_ENV !== "local" || request.headers.get("host") !== host
      || hasUntrustedNextHeaders(request.headers, host, request.nextUrl.protocol)
      || (request.headers.get("origin") && request.headers.get("origin") !== origin)) {
    return NextResponse.json({ error: "本地 API 代理拒绝了此请求。" }, { status: 403 });
  }
  const session = verifyLocalSession(request.cookies.get(LOCAL_SESSION_COOKIE)?.value);
  if (!session) return NextResponse.json({ error: "本机工作台会话已失效，请重新配对。" }, { status: 401 });
  if (!(["GET", "HEAD", "OPTIONS"].includes(request.method))) {
    if (request.headers.get("origin") !== origin || !request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
      return NextResponse.json({ error: "写入请求需要本机同源 JSON 请求。" }, { status: 403 });
    }
    const supplied = request.headers.get("x-csrf-token") ?? request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
    if (!safeEqualText(supplied, session.csrfToken)) return NextResponse.json({ error: "本地 CSRF 校验失败，请刷新后重试。" }, { status: 403 });
  }
  const apiBase = process.env.LOCAL_API_BASE_URL ?? `http://127.0.0.1:${process.env.LOCAL_API_PORT ?? "8015"}`;
  if (!isLoopbackTarget(apiBase)) return NextResponse.json({ error: "本地 API 目标配置无效。" }, { status: 503 });
  const { path } = await context.params;
  if (!path.length || path.some((part) => part === "." || part === ".." || part.includes("\\"))) return NextResponse.json({ error: "API 路径无效。" }, { status: 400 });
  const upstream = new URL(`/api/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, `${apiBase}/`);
  const headers = new Headers({ Accept: request.headers.get("accept") ?? "application/json", "X-OR-Local-Proxy": process.env.LOCAL_PROXY_TOKEN ?? "" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("X-Request-ID", requestId);
  let response: Response;
  try {
    response = await fetch(upstream, { method: request.method, headers, body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(), cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(20_000) });
  } catch {
    return NextResponse.json({ error: "本地 API 暂不可用，请检查 scripts/local.sh status。" }, { status: 503 });
  }
  const outputHeaders = new Headers({ "Cache-Control": "no-store" });
  for (const name of ["content-type", "x-request-id"]) { const value = response.headers.get(name); if (value) outputHeaders.set(name, value); }
  return new NextResponse(response.body, { status: response.status, headers: outputHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
