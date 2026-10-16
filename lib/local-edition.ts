import { apiRequest } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";

export async function localRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getAccessToken();
  if (!token) throw new Error("本地会话已失效，请重新配对。");
  return apiRequest<T>(path, { ...init, credentials: "same-origin", cache: "no-store" }, token);
}

export function formatLocalDate(value?: string | null): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}
