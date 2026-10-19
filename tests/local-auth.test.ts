import { afterEach, expect, it, vi } from "vitest";
import { getAccessToken } from "@/lib/auth";

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
it("silently bootstraps a local session with guarded POST before returning CSRF", async () => {
  vi.stubEnv("NEXT_PUBLIC_APP_MODE", "local");
  const fetcher = vi.fn(async (_url: string, init?: RequestInit) => Response.json(init?.method === "POST" ? { authenticated: true, csrf_token: "csrf-for-test" } : { authenticated: false }));
  vi.stubGlobal("fetch", fetcher);
  expect(await getAccessToken()).toBe("csrf-for-test");
  expect(fetcher).toHaveBeenCalledWith("/api/local/session", expect.objectContaining({ method: "POST", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json", "X-Local-Session-Init": "1" } }));
});
it("shares concurrent local bootstrap to prevent racing session cookies", async () => {
  vi.stubEnv("NEXT_PUBLIC_APP_MODE", "local");
  const fetcher = vi.fn(async () => Response.json({ authenticated: true, csrf_token: "csrf-for-test" }));
  vi.stubGlobal("fetch", fetcher);
  expect(await Promise.all([getAccessToken(), getAccessToken(), getAccessToken()])).toEqual(["csrf-for-test", "csrf-for-test", "csrf-for-test"]);
  expect(fetcher).toHaveBeenCalledTimes(1);
});
