import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { middleware } from "@/middleware";

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_APP_MODE", "local");
  vi.stubEnv("LOCAL_UI_ORIGIN", "http://localhost:3004");
});
afterEach(() => { vi.unstubAllEnvs(); vi.restoreAllMocks(); });
const request = (path: string, headers = {}) => new NextRequest(`http://localhost:3004${path}`, { headers: { host: "localhost:3004", ...headers } });

describe("local entry without pairing", () => {
  it("opens the dashboard without a cookie", async () => {
    const response = await middleware(request("/dashboard"));
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
  it.each(["/", "/pair", "/login"])("redirects %s directly to dashboard without a ticket", async path => {
    expect((await middleware(request(path))).headers.get("location")).toBe("http://localhost:3004/dashboard");
  });
  it.each([{ host: "evil.example" }, { origin: "https://evil.example" }, { "sec-fetch-site": "cross-site" }, { "x-forwarded-for": "192.0.2.1" }])("rejects untrusted local entry %j", async headers => {
    expect((await middleware(request("/dashboard", headers))).status).toBe(403);
  });
  it("keeps cloud dashboard authentication", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_MODE", "cloud");
    vi.stubEnv("NEXT_PUBLIC_AUTH_DISABLED", "false");
    vi.stubEnv("NEXT_PUBLIC_USE_MOCK", "false");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "");
    expect((await middleware(request("/dashboard"))).headers.get("location")).toBe("http://localhost:3004/login");
  });
});
