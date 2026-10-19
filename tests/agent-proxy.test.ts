import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { GET as agentGet, POST as agentPost } from "@/app/api/agent/[...path]/route";

const origin = "http://localhost:3004";
const context = { params: Promise.resolve({ path: ["sources"] }) };

function request(method = "GET", extra: Record<string, string> = {}, body?: string) {
  return new NextRequest(`${origin}/api/agent/sources`, {
    method,
    headers: { host: "localhost:3004", "sec-fetch-site": "same-origin", ...extra },
    ...(body ? { body } : {}),
  });
}

beforeEach(() => {
  vi.stubEnv("APP_ENV", "local");
  vi.stubEnv("LOCAL_UI_ORIGIN", origin);
  vi.stubEnv("LOCAL_API_BASE_URL", "http://127.0.0.1:8015");
  vi.stubEnv("LOCAL_PROXY_TOKEN", "test-only-proxy-secret");
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("Agent 接口透传（UI 端口）", () => {
  it("没有 Bearer 时直接 401，绝不回退到网页会话 cookie", async () => {
    const fetcher = vi.fn(async () => Response.json({ ok: true }));
    vi.stubGlobal("fetch", fetcher);
    const response = await agentGet(request("GET", { cookie: "or_local_session=valid-looking-cookie" }), context);
    expect(response.status).toBe(401);
    expect((await response.json()).error.code).toBe("AGENT_TOKEN_REQUIRED");
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("带 Bearer 时把 Authorization 与幂等键透传，且不向浏览器暴露 cookie", async () => {
    const fetcher = vi.fn(async () => Response.json({ items: [] }, { headers: { "idempotency-replayed": "true", "x-request-id": "req-9" } }));
    vi.stubGlobal("fetch", fetcher);
    const response = await agentPost(request("POST", { authorization: "Bearer or_agent_test-token", "idempotency-key": "key-12345678", "content-type": "application/json" }, "{}"), context);
    expect(response.status).toBe(200);
    const [upstream, init] = fetcher.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(upstream)).toBe("http://127.0.0.1:8015/api/agent/sources");
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer or_agent_test-token");
    expect(headers.get("Idempotency-Key")).toBe("key-12345678");
    expect(headers.get("X-OR-Local-Proxy")).toBe("test-only-proxy-secret");
    expect(response.headers.get("idempotency-replayed")).toBe("true");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it.each<Record<string, string>>([
    { host: "evil.example" },
    { "x-forwarded-for": "192.0.2.9" },
    { origin: "https://evil.example" },
    { "sec-fetch-site": "cross-site" },
  ])("拒绝不可信来源 %j", async headers => {
    const fetcher = vi.fn(async () => Response.json({}));
    vi.stubGlobal("fetch", fetcher);
    const response = await agentGet(request("GET", { authorization: "Bearer or_agent_test-token", ...headers }), context);
    expect(response.status).toBe(403);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("云端模式下不暴露 Agent 透传", async () => {
    vi.stubEnv("APP_ENV", "production");
    const response = await agentGet(request("GET", { authorization: "Bearer or_agent_test-token" }), context);
    expect(response.status).toBe(403);
  });
});
