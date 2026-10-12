import { api, useMockMode } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { toBrief } from "@/lib/transform";
import { mockBrief } from "@/data/mock-profile";
import type { DailyBrief } from "@/types/domain";

const emptyBrief: DailyBrief = { scanned: 0, found: 0, recommended: 0, potentialIncome: [0, 0], trends: [], avoid: "", actions: [] };

export async function getBrief(): Promise<DailyBrief> {
  if (useMockMode) return mockBrief;
  const token = await getAccessToken();
  if (!token) return emptyBrief;
  return toBrief(await api.brief(token));
}
