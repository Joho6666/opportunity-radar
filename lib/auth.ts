"use client";
import { createClient } from "@/lib/supabase/client";
export async function getAccessToken(): Promise<string | null> {
  const client = createClient();
  if (!client) return null;
  const { data } = await client.auth.getSession();
  return data.session?.access_token ?? null;
}
export async function signOut(): Promise<void> {
  const client = createClient();
  if (client) await client.auth.signOut();
}
