"use client";
import { createClient } from "@/lib/supabase/client";
let localSessionRequest: Promise<string | null> | null = null;
async function bootstrapLocalSession(): Promise<string | null> {
  const response = await fetch("/api/local/session", {
    method: "POST", cache: "no-store", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-Local-Session-Init": "1" }, body: "{}",
  }).catch(() => null);
  if (!response?.ok) return null;
  const session = await response.json().catch(() => null) as { authenticated?: boolean; csrf_token?: string } | null;
  return session?.authenticated && session.csrf_token ? session.csrf_token : null;
}
export async function getAccessToken(): Promise<string | null> {
  if (process.env.NEXT_PUBLIC_APP_MODE === "local") {
    // Share only in-flight requests, not tokens: cleared/expired cookies recover
    // automatically on the next call, without a pairing page or stale CSRF cache.
    localSessionRequest ??= bootstrapLocalSession().finally(() => { localSessionRequest = null; });
    return localSessionRequest;
  }
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
