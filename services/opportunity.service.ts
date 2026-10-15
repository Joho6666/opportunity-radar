import { api, apiRequest, useMockMode } from "@/lib/api-client";
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

export async function actOpportunity(id: string, status: OpportunityStatus, actualRevenue?: number): Promise<Opportunity | undefined> {
  const action = statusActionMap[status];

  if (useMockMode) {
    const item = mockOpportunities.find((opportunity) => opportunity.id === id);
    if (item) { item.status = status; if (typeof actualRevenue === "number") item.actualRevenue = actualRevenue; }
    return item;
  }
  const token = await getAccessToken();
  if (!token) throw new Error("尚未登录");
  if (!action) return toOpportunity(await apiRequest(`/api/pipeline/${id}`, { method: "PATCH", body: JSON.stringify({status, ...(typeof actualRevenue === "number" ? {actual_revenue:actualRevenue} : {})}) }, token));
  return toOpportunity(await api.opportunities.action(id, action, token, typeof actualRevenue === "number" ? { actual_revenue: actualRevenue } : {}));
}

export async function analyzeOpportunity(id: string) {
  if (useMockMode) return mockOpportunities.find((item) => item.id === id);
  const token = await getAccessToken();
  if (!token) return undefined;
  return toOpportunity(await api.opportunities.get(id, token));
}
