import type { Opportunity, Profile, Radar } from "@/types/domain";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8011";
export const useMockMode = process.env.NEXT_PUBLIC_USE_MOCK !== "false";
class ApiError extends Error { constructor(message: string, public readonly code = "API_ERROR") { super(message); } }
async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers } });
  if (!response.ok) { const payload = await response.json().catch(() => null); throw new ApiError(payload?.error?.message ?? "请求失败", payload?.error?.code); }
  return response.json() as Promise<T>;
}
export const api = {
  profile: { get: (token: string) => request<Profile>("/api/profile", {}, token), put: (value: unknown, token: string) => request<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(value) }, token), analyze: (text: string, token: string) => request("/api/profile/analyze", { method: "POST", body: JSON.stringify({ text }) }, token) },
  radars: { list: (token: string) => request<Radar[]>("/api/radars", {}, token), create: (value: unknown, token: string) => request<Radar>("/api/radars", { method: "POST", body: JSON.stringify(value) }, token), run: (id: string, token: string) => request(`/api/radars/${id}/run`, { method: "POST" }, token), pause: (id: string, token: string) => request<Radar>(`/api/radars/${id}/pause`, { method: "POST" }, token), resume: (id: string, token: string) => request<Radar>(`/api/radars/${id}/resume`, { method: "POST" }, token) },
  opportunities: { list: (token: string, query = "") => request<Opportunity[]>(`/api/opportunities${query}`, {}, token), get: (id: string, token: string) => request<Opportunity>(`/api/opportunities/${id}`, {}, token), action: (id: string, action: string, token: string, payload = {}) => request<Opportunity>(`/api/opportunities/${id}/${action}`, { method: "POST", body: JSON.stringify(payload) }, token) },
  dashboard: (token: string) => request("/api/dashboard", {}, token), brief: (token: string) => request("/api/daily-brief", {}, token), pipelineSummary: (token: string) => request("/api/pipeline/summary", {}, token)
};
