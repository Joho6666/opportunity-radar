import { afterEach, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase/client", () => ({ createClient: () => ({ auth: { getSession: async () => ({ data: { session: { access_token: "offline-contract-token" } } }) } }) }));
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.resetModules(); });

it("uses the authenticated API in production even when the demo flag is misconfigured", async () => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("NEXT_PUBLIC_USE_MOCK", "true");
  vi.stubEnv("NEXT_PUBLIC_AUTH_DISABLED", "true");
  vi.resetModules();
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal("fetch", fetcher);
  const { listOpportunities } = await import("@/services/opportunity.service");
  expect(await listOpportunities()).toEqual([]);
  expect(fetcher).toHaveBeenCalledWith(expect.stringContaining("/api/opportunities"), expect.objectContaining({
    headers: expect.objectContaining({ Authorization: "Bearer offline-contract-token" }),
  }));
});
