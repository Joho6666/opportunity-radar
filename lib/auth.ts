"use client";
import { createClient } from "@/lib/supabase/client";
export async function getAccessToken(): Promise<string | null> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_AUTH_DISABLED === "true") return "local-disabled";
  const client = createClient();
  if (!client) return null;
  const { data } = await client.auth.getSession();
  return data.session?.access_token ?? null;
}
export async function signOut(): Promise<void> {
  if (process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_AUTH_DISABLED === "true") return;
  const client = createClient();
  if (client) await client.auth.signOut();
}
