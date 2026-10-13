"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { mockOpportunities } from "@/data/mock-opportunities";
import { mockProfile, mockSkills } from "@/data/mock-profile";
import { mockRadars } from "@/data/mock-radars";
import { actOpportunity, listOpportunities } from "@/services/opportunity.service";
import { listRadars, runRadar, setRadarPaused } from "@/services/radar.service";
import { getProfile, saveProfile } from "@/services/profile.service";
import { useMockMode } from "@/lib/api-client";
import type { Opportunity, OpportunityStatus, Profile, Radar, Skill } from "@/types/domain";

type AppState = { opportunities: Opportunity[]; radars: Radar[]; profile: Profile; skills: Skill[]; hydrated: boolean; loading: boolean; error: string | null; hydrate: (force?: boolean) => Promise<void>; retry: () => Promise<void>; updateOpportunity: (id: string, status: OpportunityStatus, actualRevenue?: number) => Promise<boolean>; toggleSaved: (id: string) => Promise<void>; toggleSkill: (id: string) => void; toggleRadar: (id: string) => Promise<void>; runRadarNow: (id: string) => Promise<void>; addRadar: (radar: Radar) => void; updateProfile: (profile: Profile) => Promise<void>; reset: () => void; };
const emptyProfile: Profile = { name: "", identity: "", skills: [], skillLevels: {}, goals: [], location: "", workModes: [], monthlyIncomeGoal: 0, minimumProjectBudget: 0, availableHoursPerDay: 0, excludedOpportunityTypes: [] };
const seed = useMockMode ? { opportunities: mockOpportunities, radars: mockRadars, profile: mockProfile, skills: mockSkills } : { opportunities: [], radars: [], profile: emptyProfile, skills: [] };
// API business records must come from the authenticated server, never a shared browser
// cache that might belong to a demo or another user. Keep only local skill preferences.
// Demo data may persist, but loading/error flags must never block a later hydration.
type Persisted = Partial<AppState>;
export function persistable(state: Persisted, mockMode = useMockMode): Persisted {
  const rest = { ...state };
  delete rest.hydrated;
  delete rest.loading;
  delete rest.error;
  return mockMode ? { ...rest, hydrated: state.hydrated } : (state.skills ? { skills: state.skills } : {});
}
export function mergePersisted<T extends Persisted>(persisted: unknown, current: T, mockMode = useMockMode): T {
  return { ...current, ...persistable((persisted ?? {}) as Persisted, mockMode) };
}

const failureMessage = (error: unknown) => error instanceof Error ? error.message : "操作失败，请重试";

export const useOpportunityStore = create<AppState>()(persist((set, get) => ({ ...seed, hydrated: false, loading: false, error: null,
  hydrate: async (force = false) => {
    if (get().loading || (get().hydrated && !force)) return;
    set({ loading: true, error: null });
    try {
      const [opportunities, radars, profile] = await Promise.all([listOpportunities(), listRadars(), getProfile(get().profile)]);
      set({ opportunities, radars, profile: profile.name === "新用户" && !profile.skills.length ? get().profile : profile, hydrated: true, loading: false });
    } catch (error) { set({ loading: false, error: failureMessage(error) }); throw error; }
  },
  retry: async () => get().hydrate(true),
  updateOpportunity: async (id, status, actualRevenue) => {
    const previous = get().opportunities;
    set({ loading: true, error: null });
    try {
      await actOpportunity(id, status, actualRevenue);
      const opportunities = await listOpportunities();
      set({ opportunities, loading: false });
      return true;
    } catch (error) { set({ opportunities: previous, loading: false, error: failureMessage(error) }); return false; }
  },
  toggleSaved: async (id) => { const current = get().opportunities.find((item) => item.id === id); if (current) await get().updateOpportunity(id, current.status === "saved" ? "new" : "saved"); },
  toggleSkill: (id) => set((state) => ({ skills: state.skills.map((item) => item.id === id ? { ...item, installed: !item.installed } : item) })),
  toggleRadar: async (id) => { const radar = get().radars.find((item) => item.id === id); if (!radar) return; const previous = get().radars; const shouldPause = radar.status === "active" || radar.status === "running"; set({ loading: true, error: null }); try { await setRadarPaused(id, shouldPause); const radars = await listRadars(); set({ radars, loading: false }); } catch (error) { set({ radars: previous, loading: false, error: failureMessage(error) }); throw error; } },
  runRadarNow: async (id) => { set((state) => ({ radars: state.radars.map((item) => item.id === id ? { ...item, status: "running" } : item), loading: true, error: null })); try { await runRadar(id); const [radars, opportunities] = await Promise.all([listRadars(), listOpportunities()]); set({ radars, opportunities, loading: false, hydrated: true }); } catch (error) { set({ loading: false, error: failureMessage(error) }); throw error; } },
  addRadar: (radar) => set((state) => ({ radars: [radar, ...state.radars] })),
  updateProfile: async (profile) => { const previous = get().profile; set({ profile, loading: true, error: null }); try { await saveProfile(profile); set({ loading: false }); } catch (error) { set({ profile: previous, loading: false, error: failureMessage(error) }); throw error; } },
  reset: () => set({ ...seed, hydrated: false, loading: false, error: null })
}), {
  name: "opportunity-radar-v3",
  partialize: (state) => persistable(state),
  merge: (persisted, current) => mergePersisted(persisted, current),
}));
