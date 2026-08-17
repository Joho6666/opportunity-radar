import { api, useMockMode } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { toBrief } from "@/lib/transform";
import { mockBrief } from "@/data/mock-profile";
import type { DailyBrief } from "@/types/domain";

export async function getBrief(): Promise<DailyBrief> {
  if (useMockMode) return mockBrief;
  const token = await getAccessToken();
  if (!token) return mockBrief;
  return toBrief(await api.brief(token));
}
