import { api, useMockMode } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { toRadar } from "@/lib/transform";
import { mockRadars } from "@/data/mock-radars";
import type { Radar } from "@/types/domain";
import type { CollectionPolicy } from "@/lib/collection-policy";

export async function listRadars(): Promise<Radar[]> {
  if (useMockMode) return mockRadars;
  const token = await getAccessToken();
  if (!token) return [];
  return (await api.radars.list(token)).map(toRadar);
}

export async function createRadar(input: { name: string; goal: string; description?: string; keywords?: string[]; locations?: string[]; minimumBudget?: number; frequency?: string; freshnessHours?: number; collectionPolicy?: CollectionPolicy; sources?: string[]; listenerDescription?: string }): Promise<Radar> {
  if (useMockMode) {
    const id = `radar-${Date.now()}`;
    return { id, name: input.name, description: input.description ?? input.goal, status: "active", goal: input.goal, keywords: input.keywords ?? [], locations: input.locations ?? [], minimumBudget: input.minimumBudget ?? 0, frequency: input.frequency ?? "manual", sources: (input.sources ?? ["web"]) as Radar["sources"], lastRunAt: "从未运行", nextRunAt: "手动运行", stats: { scanned: 0, found: 0, matched: 0, recommended: 0 } };
  }
  const token = await getAccessToken();
  if (!token) throw new Error("尚未登录");
  return toRadar(await api.radars.create({
    name: input.name,
    goal: input.goal,
    description: input.description ?? input.goal,
    keywords: input.keywords ?? [],
    locations: input.locations ?? [],
    minimum_budget: input.minimumBudget ?? 0,
    frequency: input.frequency ?? "manual",
    freshness_hours: input.freshnessHours ?? 72,
    ...(input.collectionPolicy ? {collection_policy:input.collectionPolicy} : {}),
    sources: input.sources ?? ["github"],
    listener_description: input.listenerDescription ?? input.goal,
  }, token));
}

export async function updateRadarCollection(radar: Radar, input: {keywords:string[];freshnessHours:number;collectionPolicy:CollectionPolicy;minimumBudget:number}):Promise<void> {
  if (useMockMode) throw new Error("演示模式不保存真实采集配置");
  const token = await getAccessToken();
  if (!token) throw new Error("尚未登录");
  const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8011";
  const response = await fetch(`${baseUrl}/api/radars/${radar.id}`, {method:"PUT",headers:{"Content-Type":"application/json",Authorization:`Bearer ${token}`},body:JSON.stringify({name:radar.name,description:radar.description,goal:radar.goal,keywords:input.keywords,locations:radar.locations,minimum_budget:input.minimumBudget,frequency:radar.frequency,freshness_hours:input.freshnessHours,collection_policy:input.collectionPolicy,sources:radar.sources,listener_description:radar.listenerDescription ?? ""})});
  if (!response.ok) {
    const error = await response.json().catch(()=>null);
    throw new Error(error?.error?.message ?? "保存采集配置失败");
  }
}

export async function runRadar(id: string): Promise<void> {
  if (useMockMode) return;
  const token = await getAccessToken();
  if (!token) return;
  await api.radars.run(id, token);
}

export async function setRadarPaused(id: string, paused: boolean): Promise<void> {
  if (useMockMode) return;
  const token = await getAccessToken();
  if (!token) return;
  await (paused ? api.radars.pause(id, token) : api.radars.resume(id, token));
}

export async function parseRadarIntent(input: string) { return { name: "兼职客户雷达", description: input, keywords: ["PPT", "AI 自动化", "小程序"], locations: ["桂林", "线上"], minimumBudget: 200 }; }
