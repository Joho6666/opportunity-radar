import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
vi.mock("server-only", () => ({}));
import { GET as sessionRead, POST as bootstrap } from "@/app/api/local/session/route";
import { GET as read, POST as write } from "@/app/api/[...path]/route";
import { POST as pair } from "@/app/api/local/pair/route";

const origin = "http://localhost:3004";
const context = { params: Promise.resolve({ path: ["local", "overview"] }) };
function request(path: string, method = "POST", extra = {}) {
  return new NextRequest(`${origin}${path}`, { method, headers: { host: "localhost:3004", origin, "content-type": "application/json", "x-local-session-init": "1", "sec-fetch-site": "same-origin", ...extra }, ...(method === "POST" ? { body: "{}" } : {}) });
}
beforeEach(() => {
  vi.stubEnv("APP_ENV", "local");
  vi.stubEnv("LOCAL_UI_ORIGIN", origin);
  vi.stubEnv("LOCAL_SESSION_SECRET", "test-only-session-secret-".repeat(4));
  vi.stubEnv("LOCAL_PROXY_TOKEN", "test-only-proxy-secret");
  vi.stubEnv("LOCAL_API_BASE_URL", "http://127.0.0.1:8015");
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
async function session() {
  const response = await bootstrap(request("/api/local/session"));
  expect(response.status).toBe(200);
  const cookie = response.cookies.get("or_local_session")!;
  return { cookie: `${cookie.name}=${cookie.value}`, csrf: (await response.json()).csrf_token, response };
}
describe("local automatic session and protected API", () => {
  it("creates an HttpOnly strict session without a ticket and reuses it", async () => {
    const first = await session();
    expect(first.response.headers.get("set-cookie")).toMatch(/HttpOnly/i);
    expect(first.response.headers.get("set-cookie")).toMatch(/SameSite=strict/i);
    const second = await bootstrap(request("/api/local/session", "POST", { cookie: first.cookie }));
    expect((await second.json()).csrf_token).toBe(first.csrf);
    expect(second.headers.get("set-cookie")).toBeNull();
    expect((await (await sessionRead(request("/api/local/session", "GET", { cookie: first.cookie }))).json()).authenticated).toBe(true);
  });
  it.each(["", "or_local_session=expired-or-forged"])("recovers absent or invalid cookies (%s) without a ticket", async cookie => {
    const response = await bootstrap(request("/api/local/session", "POST", { cookie }));
    expect(response.status).toBe(200);
    expect((await response.json()).authenticated).toBe(true);
    expect(response.cookies.get("or_local_session")?.value).toBeTruthy();
  });
  it.each([{ origin: "https://evil.example" }, { host: "evil.example" }, { "sec-fetch-site": "cross-site" }, { "x-forwarded-for": "192.0.2.1" }, { "x-local-session-init": "" }])("refuses bootstrap %j", async extra => {
    expect((await bootstrap(request("/api/local/session", "POST", extra))).status).toBe(403);
  });
  it("does not create local sessions in cloud mode", async () => {
    vi.stubEnv("APP_ENV", "production");
    const response = await bootstrap(request("/api/local/session"));
    expect(response.status).toBe(403);
    expect(response.headers.get("set-cookie")).toBeNull();
  });
  it("reads authenticated API and forwards only the server proxy credential", async () => {
    const { cookie } = await session();
    const fetcher = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetcher);
    expect((await read(request("/api/local/overview", "GET", { cookie }), context)).status).toBe(200);
    const headers = fetcher.mock.calls[0] as unknown as [URL, RequestInit];
    expect(new Headers(headers[1].headers).get("X-OR-Local-Proxy")).toBe("test-only-proxy-secret");
    expect((await read(request("/api/local/overview", "GET"), context)).status).toBe(401);
  });
  it("keeps writes protected and permits the same-origin CSRF-authorized write", async () => {
    const { cookie, csrf } = await session();
    const fetcher = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetcher);
    expect((await write(request("/api/local/overview", "POST", { cookie }), context)).status).toBe(403);
    expect((await write(request("/api/local/overview", "POST", { cookie, authorization: `Bearer ${csrf}`, origin: "https://evil.example" }), context)).status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
    expect((await write(request("/api/local/overview", "POST", { cookie, authorization: `Bearer ${csrf}` }), context)).status).toBe(200);
  });
  it("retires ticket-based pairing instead of leaving a second session issuer", async () => {
    expect((await pair()).status).toBe(410);
  });
});
