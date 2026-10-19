import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { agentTokenStatusText, fetchAgentToken, generateAgentToken, maskAgentToken, revokeAgentToken, type AgentTokenState } from "../lib/local-agent";

const STATE: AgentTokenState = { configured: true, masked_token: "or_agent_1***cdef", created_at: "2026-10-16T00:00:00Z", updated_at: "2026-10-16T00:00:00Z", rotations: 2, path_configured: true, restart_required: false };

describe("Agent 令牌掩码与状态文案", () => {
  it("掩码只保留前缀与末四位，绝不暴露全文", () => {
    const token = "or_agent_abcdefghijklmnopqrstuvwxyz0123456789";
    const masked = maskAgentToken(token);
    expect(masked.startsWith("or_agent_a")).toBe(true);
    expect(masked.endsWith(token.slice(-4))).toBe(true);
    expect(masked).toContain("***");
    expect(masked).not.toBe(token);
    expect(masked.length).toBeLessThan(token.length);
    expect(token.slice(10, -4)).not.toContain("*");
    expect(masked.includes(token.slice(10, -4))).toBe(false);
  });
  it("短令牌与空值安全降级", () => {
    expect(maskAgentToken("")).toBe("");
    expect(maskAgentToken("or_agent_short")).toBe("or_agent_***");
  });
  it("状态文案覆盖未配置与已配置两种状态", () => {
    expect(agentTokenStatusText(null)).toContain("未配置");
    expect(agentTokenStatusText({ ...STATE, configured: false, masked_token: "" })).toContain("未配置");
    expect(agentTokenStatusText(STATE)).toContain(STATE.masked_token);
    expect(agentTokenStatusText(STATE)).toContain("无需重启");
  });
});

describe("本地会话下的令牌接口调用", () => {
  beforeEach(() => {
    vi.stubEnv("NEXT_PUBLIC_APP_MODE", "local");
    vi.stubEnv("NEXT_PUBLIC_AUTH_DISABLED", "false");
    vi.stubEnv("NEXT_PUBLIC_USE_MOCK", "false");
  });
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  function stubFetch(agentPayload: unknown, status = 200) {
    const calls: { url: string; init: RequestInit }[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init: init ?? {} });
      if (url.includes("/api/local/session")) return Response.json({ authenticated: true, csrf_token: "csrf-token" });
      return Response.json(agentPayload, { status });
    });
    vi.stubGlobal("fetch", fetcher);
    return calls;
  }

  it("读取令牌状态：GET /api/local/agent-token，且响应不含明文", async () => {
    const calls = stubFetch(STATE);
    const state = await fetchAgentToken();
    expect(state.configured).toBe(true);
    expect(state.masked_token).toBe(STATE.masked_token);
    expect(JSON.stringify(state)).not.toContain("plaintext");
    const agentCall = calls.find((call) => call.url.includes("/api/local/agent-token"))!;
    expect(agentCall.init.method ?? "GET").toBe("GET");
  });

  it("生成令牌：POST 且只把一次性明文交给调用方，写入本地配置由后端负责", async () => {
    const calls = stubFetch({ ...STATE, plaintext: "or_agent_plaintext-once", notice: "只显示一次" });
    const generated = await generateAgentToken();
    expect(generated.plaintext).toBe("or_agent_plaintext-once");
    expect(generated.masked_token).toBe(STATE.masked_token);
    expect(calls).toHaveLength(2); // 会话 bootstrap + 生成请求
    const agentCall = calls.find((call) => call.url.includes("/api/local/agent-token"))!;
    expect(agentCall.init.method).toBe("POST");
    expect(new Headers(agentCall.init.headers).get("Authorization")).toBe("Bearer csrf-token");
  });

  it("吊销令牌：DELETE 并把失败信息抛给调用方", async () => {
    const calls = stubFetch({ ...STATE, configured: false, masked_token: "" });
    const revoked = await revokeAgentToken();
    expect(revoked.configured).toBe(false);
    expect(calls.find((call) => call.url.includes("/api/local/agent-token"))!.init.method).toBe("DELETE");

    stubFetch({ error: { code: "AGENT_API_LOCAL_ONLY", message: "仅本机版" } }, 403);
    await expect(revokeAgentToken()).rejects.toThrowError("仅本机版");
  });
});
