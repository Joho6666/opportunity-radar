import { NextRequest, NextResponse } from "next/server";
import { hasUntrustedNextHeaders } from "@/lib/local-request-guards";

/** Agent 接口的 UI 端口透传：http://localhost:3004/api/agent/* → 127.0.0.1:<LOCAL_API_PORT>/api/agent/*
 *
 * 与网页会话链路完全隔离：不读取、不校验也没有任何 cookie 回退；只接受 Authorization: Bearer，
 * 令牌校验在后端完成（同一 Host/Origin/loopback 校验在两侧都执行）。 */
export const runtime = "nodejs";

function errorResponse(code: string, message: string, status: number) {
  return NextResponse.json({ error: { code, message } }, { status, headers: { "Cache-Control": "no-store" } });
}

function isLoopbackTarget(value: string): boolean {
  try {
    const target = new URL(value);
    const expectedPort = process.env.LOCAL_API_PORT ?? "8015";
    return target.protocol === "http:" && target.hostname === "127.0.0.1" && target.port === expectedPort && !target.username && !target.password;
  } catch { return false; }
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const origin = process.env.LOCAL_UI_ORIGIN ?? "http://localhost:3004";
  const host = new URL(origin).host;
  if (process.env.APP_ENV !== "local" || request.headers.get("host") !== host
      || hasUntrustedNextHeaders(request.headers, host, request.nextUrl.protocol)
      || (request.headers.get("origin") && request.headers.get("origin") !== origin)
      || request.headers.get("sec-fetch-site") === "cross-site") {
    return errorResponse("AGENT_LOCAL_ONLY", "Agent 接口只接受本机同源请求；请勿经代理或公网访问。", 403);
  }
  const authorization = request.headers.get("authorization") ?? "";
  if (!/^bearer\s+\S+/i.test(authorization)) {
    return errorResponse("AGENT_TOKEN_REQUIRED", "缺少 Bearer Token：Agent 接口不使用网页会话，请在请求头附带 Authorization: Bearer <token>。", 401);
  }
  const apiBase = process.env.LOCAL_API_BASE_URL ?? `http://127.0.0.1:${process.env.LOCAL_API_PORT ?? "8015"}`;
  if (!isLoopbackTarget(apiBase)) return errorResponse("AGENT_API_MISCONFIGURED", "本地 API 目标配置无效。", 503);
  const { path } = await context.params;
  if (!path.length || path.some((part) => part === "." || part === ".." || part.includes("\\"))) return errorResponse("AGENT_PATH_INVALID", "API 路径无效。", 400);
  const upstream = new URL(`/api/agent/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`, `${apiBase}/`);
  const headers = new Headers({ Accept: request.headers.get("accept") ?? "application/json", Authorization: authorization, "X-OR-Local-Proxy": process.env.LOCAL_PROXY_TOKEN ?? "" });
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers.set("X-Request-ID", requestId);
  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  let response: Response;
  try {
    response = await fetch(upstream, { method: request.method, headers, body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(), cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(30_000) });
  } catch {
    return errorResponse("AGENT_API_UNAVAILABLE", "本地 API 暂不可用，请检查 scripts/local.sh status。", 503);
  }
  const outputHeaders = new Headers({ "Cache-Control": "no-store" });
  for (const name of ["content-type", "x-request-id", "idempotency-replayed"]) { const value = response.headers.get(name); if (value) outputHeaders.set(name, value); }
  return new NextResponse(response.body, { status: response.status, headers: outputHeaders });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
