import "server-only";
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const LOCAL_SESSION_COOKIE = "or_local_session";
export const LOCAL_SESSION_TTL_SECONDS = 60 * 60 * 24 * 30;

function secret(): Buffer {
  const value = process.env.LOCAL_SESSION_SECRET ?? "";
  if (value.length < 64) throw new Error("Local session secret is not configured");
  return Buffer.from(value, "utf8");
}

function signature(value: string): Buffer {
  return createHmac("sha256", secret()).update(value).digest();
}

export function createLocalSession(): { value: string; csrfToken: string } {
  const nonce = randomBytes(32).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ nonce, expires: Math.floor(Date.now() / 1000) + LOCAL_SESSION_TTL_SECONDS })).toString("base64url");
  return { value: `${payload}.${signature(payload).toString("base64url")}`, csrfToken: createHmac("sha256", secret()).update(`csrf:${nonce}`).digest("base64url") };
}

export function verifyLocalSession(value: string | undefined): { csrfToken: string } | null {
  if (!value) return null;
  try {
    const [payload, encodedSignature, extra] = value.split(".");
    if (!payload || !encodedSignature || extra) return null;
    const provided = Buffer.from(encodedSignature, "base64url");
    const expected = signature(payload);
    if (provided.length !== expected.length || !timingSafeEqual(provided, expected)) return null;
    const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as { nonce?: unknown; expires?: unknown };
    if (typeof decoded.nonce !== "string" || typeof decoded.expires !== "number" || decoded.expires <= Math.floor(Date.now() / 1000)) return null;
    return { csrfToken: createHmac("sha256", secret()).update(`csrf:${decoded.nonce}`).digest("base64url") };
  } catch {
    return null;
  }
}

export function safeEqualText(left: string, right: string): boolean {
  const a = Buffer.from(left, "utf8");
  const b = Buffer.from(right, "utf8");
  return a.length === b.length && timingSafeEqual(a, b);
}
