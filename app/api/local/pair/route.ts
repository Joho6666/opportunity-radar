import { createHash } from "node:crypto";
import { readFileSync, unlinkSync, openSync, closeSync, writeFileSync, existsSync } from "node:fs";
import { NextRequest, NextResponse } from "next/server";
import { createLocalSession, LOCAL_SESSION_COOKIE, LOCAL_SESSION_TTL_SECONDS, safeEqualText } from "@/lib/server/local-session";
import { hasUntrustedNextHeaders } from "@/lib/local-request-guards";

export const runtime = "nodejs";

function allowedRequest(request: NextRequest): boolean {
  const origin = process.env.LOCAL_UI_ORIGIN ?? "http://localhost:3004";
  const url = new URL(origin);
  return request.headers.get("host") === url.host
    && request.headers.get("origin") === origin
    && !hasUntrustedNextHeaders(request.headers, url.host, request.nextUrl.protocol);
}

export async function POST(request: NextRequest) {
  if (process.env.APP_ENV !== "local") return NextResponse.json({ error: "本地配对不可用。" }, { status: 404 });
  if (!allowedRequest(request) || !request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return NextResponse.json({ error: "本地配对请求来源无效。" }, { status: 403 });
  }
  let ticket = "";
  try { ticket = String((await request.json() as { ticket?: unknown }).ticket ?? ""); } catch { /* rejected below */ }
  const ticketPath = process.env.LOCAL_PAIRING_TOKEN_PATH ?? "";
  if (!ticketPath || ticket.length < 32 || !existsSync(ticketPath)) return NextResponse.json({ error: "配对码不存在或已过期，请重新运行 local.sh pair。" }, { status: 401 });
  const lockPath = `${ticketPath}.lock`;
  let lock = -1;
  try {
    lock = openSync(lockPath, "wx", 0o600);
    const [digest, expiresAt] = readFileSync(ticketPath, "utf8").trim().split("\n");
    const supplied = createHash("sha256").update(ticket).digest("hex");
    if (!expiresAt || Number(expiresAt) < Date.now() || !safeEqualText(digest, supplied)) {
      return NextResponse.json({ error: "配对码无效或已过期。" }, { status: 401 });
    }
    unlinkSync(ticketPath);
    const pairedMarker = process.env.LOCAL_PAIRED_MARKER_PATH;
    if (pairedMarker) writeFileSync(pairedMarker, `${new Date().toISOString()}\n`, { mode: 0o600 });
  } catch {
    return NextResponse.json({ error: "配对码已使用或正在配对，请重试。" }, { status: 409 });
  } finally {
    if (lock >= 0) closeSync(lock);
    if (lock >= 0) { try { unlinkSync(lockPath); } catch { /* the lock may have expired */ } }
  }
  const session = createLocalSession();
  const response = NextResponse.json({ authenticated: true, csrf_token: session.csrfToken });
  response.cookies.set(LOCAL_SESSION_COOKIE, session.value, { httpOnly: true, sameSite: "strict", path: "/", maxAge: LOCAL_SESSION_TTL_SECONDS });
  response.headers.set("Cache-Control", "no-store");
  return response;
}
