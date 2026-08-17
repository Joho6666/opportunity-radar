import { api, useMockMode } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";
import { fromProfile, toProfile } from "@/lib/transform";
import { mockProfile } from "@/data/mock-profile";
import type { Profile } from "@/types/domain";

export async function getProfile(previous?: Profile): Promise<Profile> {
  if (useMockMode) return mockProfile;
  const token = await getAccessToken();
  if (!token) return previous ?? mockProfile;
  return toProfile(await api.profile.get(token), previous);
}

export async function saveProfile(profile: Profile): Promise<void> {
  if (useMockMode) return;
  const token = await getAccessToken();
  if (!token) return;
  await api.profile.put(fromProfile(profile), token);
}
