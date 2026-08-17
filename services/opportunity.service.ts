import { api, useMockMode } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { statusActionMap, toOpportunity } from "@/lib/transform";
import { mockOpportunities } from "@/data/mock-opportunities";
import type { Opportunity, OpportunityStatus } from "@/types/domain";

export async function listOpportunities(): Promise<Opportunity[]> {
  if (useMockMode) return mockOpportunities;
  const token = await getAccessToken();
  if (!token) return [];
  return (await api.opportunities.list(token)).map(toOpportunity);
}

export async function actOpportunity(id: string, status: OpportunityStatus): Promise<void> {
  const action = statusActionMap[status];
  if (!action) return;
  const token = await getAccessToken();
  if (!token) return;
  await api.opportunities.action(id, action, token);
}

export async function analyzeOpportunity(id: string) { return mockOpportunities.find((item) => item.id === id); }
