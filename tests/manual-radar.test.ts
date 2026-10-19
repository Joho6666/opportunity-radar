import { beforeEach, expect, it, vi } from "vitest";
vi.mock("../lib/local-edition", () => ({ localRequest: vi.fn() }));
import { localRequest } from "../lib/local-edition";
import { runManualRadar } from "../lib/manual-radar";
const request = vi.mocked(localRequest);
beforeEach(() => request.mockReset());

const PROVIDERS = {
  tikhub: { configured: true, enabled: true, key_source: "ui", masked_key: "sk-***0001", budgets: { single_run_limit_usd: 0.1, daily_limit_usd: 1, daily_request_limit: 20, confirm_required: true }, last_test: null },
  placeholders: [],
};

it("persists and reads back bounded manual authorization before dispatch", async () => {
  request.mockResolvedValueOnce({ items: [{ id: "xiaohongshu", available: true, provider: "tikhub" }] })
    .mockResolvedValueOnce(PROVIDERS)
    .mockResolvedValueOnce({}).mockResolvedValueOnce({ authorizations: [{ scope: "radar", enabled: true, allow_scheduled: false }] }).mockResolvedValueOnce({ id: "run" });
  expect(await runManualRadar({ id: "radar", sources: ["xiaohongshu"] })).toEqual({ id: "run" });
  expect(request.mock.calls[1][0]).toBe("/api/local/providers");
  const payload = JSON.parse(request.mock.calls[2][1]!.body as string);
  expect(payload).toEqual({ enabled: true, providers: ["tikhub"], allow_scheduled: false, run_requests: 10, daily_requests: 20, run_cost_usd: 0.1, daily_cost_usd: 1 });
  expect(request.mock.calls[3][0]).toBe("/api/billing/status");
  expect(request.mock.calls[4][0]).toBe("/api/radars/radar/run");
});

it("uses interface-configured budgets instead of hardcoded ones", async () => {
  request.mockResolvedValueOnce({ items: [{ id: "douyin", available: true, provider: "tikhub" }] })
    .mockResolvedValueOnce({ ...PROVIDERS, tikhub: { ...PROVIDERS.tikhub, budgets: { single_run_limit_usd: 0.05, daily_limit_usd: 0.5, daily_request_limit: 8, confirm_required: false } } })
    .mockResolvedValueOnce({}).mockResolvedValueOnce({ authorizations: [{ scope: "radar", enabled: true, allow_scheduled: false }] }).mockResolvedValueOnce({ id: "run" });
  await runManualRadar({ id: "radar", sources: ["douyin"] });
  const payload = JSON.parse(request.mock.calls[2][1]!.body as string);
  expect(payload).toEqual({ enabled: true, providers: ["tikhub"], allow_scheduled: false, run_requests: 8, daily_requests: 8, run_cost_usd: 0.05, daily_cost_usd: 0.5 });
});

it("never dispatches an unpriced or unintegrated source", async () => {
  request.mockResolvedValueOnce({ items: [{ id: "weibo", available: false, provider: "tikhub" }] });
  await expect(runManualRadar({ id: "radar", sources: ["weibo"] })).rejects.toThrow("价格未核验");
  expect(request).toHaveBeenCalledTimes(1);
});

it("never dispatches if persisted authorization is absent", async () => {
  request.mockResolvedValueOnce({ items: [{ id: "xiaohongshu", available: true, provider: "tikhub" }] }).mockResolvedValueOnce(PROVIDERS).mockResolvedValueOnce({}).mockResolvedValueOnce({ authorizations: [] });
  await expect(runManualRadar({ id: "radar", sources: ["xiaohongshu"] })).rejects.toThrow("未保存");
  expect(request).toHaveBeenCalledTimes(4);
});
