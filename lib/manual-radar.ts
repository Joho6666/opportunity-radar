import { localRequest } from "./local-edition";
import { authorizationFromBudgets, fetchBudgets } from "./local-providers";
import type { HuntSource } from "./lead-hunt";

/** Called only by an explicit manual button; reuse persistent per-radar billing. */
export async function runManualRadar<T>(radar: { id: string; sources: string[] }): Promise<T> {
  const { items } = await localRequest<{ items: HuntSource[] }>("/api/local/sources");
  const selected = radar.sources.map(id => items.find(item => item.id === id));
  if (selected.some(item => !item?.available)) throw new Error("所选平台尚未配置或价格未核验，请在编辑页查看平台详情。");
  if (selected.some(item => item?.provider === "tikhub")) {
    // 每雷达授权沿用界面内配置的单轮/每日预算，仍走同一计费网关的预留与账本。
    const budgets = await fetchBudgets();
    await localRequest(`/api/billing/authorizations/${encodeURIComponent(radar.id)}`, {
      method: "PUT", body: JSON.stringify({ enabled: true, providers: ["tikhub"], allow_scheduled: false, ...authorizationFromBudgets(budgets) }),
    });
    const status = await localRequest<{ authorizations: { scope: string; enabled: boolean; allow_scheduled: boolean }[] }>("/api/billing/status");
    if (!status.authorizations.some(a => a.scope === radar.id && a.enabled && !a.allow_scheduled)) throw new Error("手动采集授权未保存。");
  }
  return localRequest<T>(`/api/radars/${encodeURIComponent(radar.id)}/run`, { method: "POST", body: "{}" });
}
