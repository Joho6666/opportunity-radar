import { beforeEach, expect, it, vi } from "vitest";
import { mockOpportunities } from "@/data/mock-opportunities";
import { mockRadars } from "@/data/mock-radars";
import { mockProfile } from "@/data/mock-profile";
const service = vi.hoisted(() => ({ list: vi.fn(), act: vi.fn(), radars: vi.fn(), run: vi.fn(), pause: vi.fn(), profile: vi.fn(), save: vi.fn() }));
vi.mock("@/lib/api-client", () => ({ useMockMode: false }));
vi.mock("@/services/opportunity.service", () => ({ listOpportunities: service.list, actOpportunity: service.act }));
vi.mock("@/services/radar.service", () => ({ listRadars: service.radars, runRadar: service.run, setRadarPaused: service.pause }));
vi.mock("@/services/profile.service", () => ({ getProfile: service.profile, saveProfile: service.save }));
vi.hoisted(() => { const values = new Map<string, string>(); Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) } }); });
import { mergePersisted, persistable, useOpportunityStore as store } from "@/stores/use-opportunity-store";
beforeEach(() => { vi.resetAllMocks(); store.getState().reset(); service.list.mockResolvedValue(mockOpportunities); service.radars.mockResolvedValue(mockRadars); service.profile.mockResolvedValue(mockProfile); });
it("reads the authoritative list after opportunity actions", async () => {
  store.setState({ opportunities: mockOpportunities });
  const expected = [{ ...mockOpportunities[0], status: "won" as const, actualRevenue: 600 }];
  service.act.mockResolvedValue({ ...mockOpportunities[0], status: "won" });
  service.list.mockResolvedValue(expected);
  await store.getState().updateOpportunity(mockOpportunities[0].id, "won", 600);
  expect(store.getState().opportunities).toEqual(expected);
});
it("returns failure without unhandled rejection for existing fire-and-forget callers", async () => {
  store.setState({ opportunities: mockOpportunities });
  service.act.mockRejectedValue(new Error("保存失败"));
  expect(await store.getState().updateOpportunity(mockOpportunities[0].id, "won")).toBe(false);
  expect(store.getState().opportunities).toEqual(mockOpportunities);
  expect(store.getState().error).toBe("保存失败");
  expect(store.getState().loading).toBe(false);
});
it("restoring an older stored state never brings back hydrated/loading/error in API mode", async () => {
  const legacy = { opportunities: [], radars: [], hydrated: true, loading: true, error: "旧错误" };
  const merged = mergePersisted(legacy, store.getState(), false);
  expect(merged.hydrated).toBe(false);
  expect(merged.loading).toBe(false);
  expect(merged.error).toBeNull();
  store.setState(merged);
  await store.getState().hydrate();
  expect(service.list).toHaveBeenCalledTimes(1);
  expect(store.getState().opportunities).toEqual(mockOpportunities);
});
it("only persists local skill preferences in API mode; demo mode keeps its records", () => {
  const state = { opportunities: mockOpportunities, hydrated: true, loading: true, error: "x" };
  const api = persistable(state, false);
  expect(api).not.toHaveProperty("opportunities");
  expect(persistable({ profile: mockProfile, radars: mockRadars, skills: [] }, false)).toEqual({ skills: [] });
  expect(api).not.toHaveProperty("hydrated");
  expect(api).not.toHaveProperty("loading");
  expect(api).not.toHaveProperty("error");
  expect(persistable(state, true)).toMatchObject({ hydrated: true });
  expect(persistable(state, true)).not.toHaveProperty("loading");
});

it("does not expose demo or another user's cached records when API hydration fails", async () => {
  const legacy = { opportunities: mockOpportunities, radars: mockRadars, profile: mockProfile, hydrated: true };
  store.setState(mergePersisted(legacy, store.getState(), false));
  service.list.mockRejectedValue(new Error("API unavailable"));
  await expect(store.getState().hydrate()).rejects.toThrow("API unavailable");
  expect(store.getState().opportunities).toEqual([]);
  expect(store.getState().radars).toEqual([]);
  expect(store.getState().profile.name).toBe("");
  expect(store.getState().hydrated).toBe(false);
  expect(store.getState().error).toBe("API unavailable");
});
