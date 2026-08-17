"use client";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { mockOpportunities } from "@/data/mock-opportunities";
import { mockProfile, mockSkills } from "@/data/mock-profile";
import { mockRadars } from "@/data/mock-radars";
import { actOpportunity, listOpportunities } from "@/services/opportunity.service";
import { listRadars, runRadar, setRadarPaused } from "@/services/radar.service";
import { getProfile, saveProfile } from "@/services/profile.service";
import type { Opportunity, OpportunityStatus, Profile, Radar, Skill } from "@/types/domain";
type AppState = { opportunities: Opportunity[]; radars: Radar[]; profile: Profile; skills: Skill[]; hydrated: boolean; hydrate: () => Promise<void>; updateOpportunity: (id: string, status: OpportunityStatus) => void; toggleSaved: (id: string) => void; toggleSkill: (id: string) => void; toggleRadar: (id: string) => void; runRadarNow: (id: string) => void; addRadar: (radar: Radar) => void; updateProfile: (profile: Profile) => void; reset: () => void; };
const seed = { opportunities: mockOpportunities, radars: mockRadars, profile: mockProfile, skills: mockSkills };
export const useOpportunityStore = create<AppState>()(persist((set, get) => ({ ...seed, hydrated: false,
  hydrate: async () => {
    if (get().hydrated) return;
    set({ hydrated: true });
    try {
      const [opportunities, radars, profile] = await Promise.all([listOpportunities(), listRadars(), getProfile(get().profile)]);
      set({ opportunities: opportunities.length ? opportunities : mockOpportunities, radars: radars.length ? radars : mockRadars, profile: profile.name === "新用户" && !profile.skills.length ? get().profile : profile });
    } catch { /* 后端不可用时保留本地数据 */ }
  },
  updateOpportunity: (id, status) => { set((state) => ({ opportunities: state.opportunities.map((item) => item.id === id ? { ...item, status } : item) })); void actOpportunity(id, status).catch(() => {}); },
  toggleSaved: (id) => { const current = get().opportunities.find((item) => item.id === id); get().updateOpportunity(id, current?.status === "saved" ? "new" : "saved"); },
  toggleSkill: (id) => set((state) => ({ skills: state.skills.map((item) => item.id === id ? { ...item, installed: !item.installed } : item) })),
  toggleRadar: (id) => { const radar = get().radars.find((item) => item.id === id); if (!radar) return; const paused = radar.status !== "running"; set((state) => ({ radars: state.radars.map((item) => item.id === id ? { ...item, status: paused ? "running" : "paused" } : item) })); void setRadarPaused(id, paused).catch(() => {}); },
  runRadarNow: (id) => { set((state) => ({ radars: state.radars.map((item) => item.id === id ? { ...item, status: "running" } : item) })); void runRadar(id).then(() => get().hydrate()).catch(() => {}); },
  addRadar: (radar) => set((state) => ({ radars: [radar, ...state.radars] })),
  updateProfile: (profile) => { set({ profile }); void saveProfile(profile).catch(() => {}); },
  reset: () => set({ ...seed, hydrated: false })
}), { name: "opportunity-radar-v2" }));
