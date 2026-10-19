/** 界面内 Provider 配置的读取辅助：预算默认值、授权请求映射与运行前确认。 */
import { localRequest } from "./local-edition";
import { MAX_RUN_REQUESTS } from "./lead-hunt";

export type ProviderBudgets = { single_run_limit_usd: number; daily_limit_usd: number; daily_request_limit: number; confirm_required: boolean };
export type ProviderTestResult = { ok: boolean; http_status: number | null; latency_ms: number; tested_at: string; message: string };
export type TikHubProviderState = {
  configured: boolean; enabled: boolean; key_source: "ui" | "env" | "none"; masked_key: string;
  budgets: ProviderBudgets; last_test: ProviderTestResult | null; updated_at?: string; restart_required?: boolean;
};
export type ProviderPlaceholder = { id: string; name: string; status: string; detail: string; available: boolean };
export type ProviderConfigResponse = { tikhub: TikHubProviderState; placeholders: ProviderPlaceholder[]; restart_required?: boolean };

/** 本机硬上限（与 local.sh / 计费网关一致）：单轮与每日 ≤ USD 1，每日 ≤ 20 请求。 */
export const LOCAL_LIMITS = { single_run_limit_usd: 1, daily_limit_usd: 1, daily_request_limit: 20 } as const;
export const FALLBACK_BUDGETS: ProviderBudgets = { single_run_limit_usd: 0.1, daily_limit_usd: 1, daily_request_limit: 20, confirm_required: true };

function boundedNumber(value: unknown, fallback: number, maximum: number): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.min(value, maximum) : fallback;
}

/** 接受 /api/local/providers 响应或 budgets 对象本身；缺字段回退默认并夹在本机上限内。 */
export function readBudgets(config: unknown): ProviderBudgets {
  const source = (config && typeof config === "object" ? ((config as { tikhub?: { budgets?: unknown } }).tikhub?.budgets ?? config) : {}) as Partial<ProviderBudgets>;
  return {
    single_run_limit_usd: boundedNumber(source.single_run_limit_usd, FALLBACK_BUDGETS.single_run_limit_usd, LOCAL_LIMITS.single_run_limit_usd),
    daily_limit_usd: boundedNumber(source.daily_limit_usd, FALLBACK_BUDGETS.daily_limit_usd, LOCAL_LIMITS.daily_limit_usd),
    daily_request_limit: Number.isInteger(source.daily_request_limit) && (source.daily_request_limit as number) >= 1
      ? Math.min(source.daily_request_limit as number, LOCAL_LIMITS.daily_request_limit) : FALLBACK_BUDGETS.daily_request_limit,
    confirm_required: typeof source.confirm_required === "boolean" ? source.confirm_required : FALLBACK_BUDGETS.confirm_required,
  };
}

export async function fetchProviderConfig(): Promise<ProviderConfigResponse> {
  return localRequest<ProviderConfigResponse>("/api/local/providers");
}

export async function fetchBudgets(): Promise<ProviderBudgets> {
  return readBudgets(await fetchProviderConfig());
}

/** 预算映射为每雷达手动授权；10 次 = 6 次首屏查询 + 视频号分享链/频道/链接附加调用。 */
export function authorizationFromBudgets(budgets: ProviderBudgets) {
  return {
    run_requests: Math.max(1, Math.min(MAX_RUN_REQUESTS, budgets.daily_request_limit)),
    daily_requests: budgets.daily_request_limit,
    run_cost_usd: budgets.single_run_limit_usd,
    daily_cost_usd: budgets.daily_limit_usd,
  };
}

export function confirmMessage(budgets: ProviderBudgets, radarName?: string): string {
  const target = radarName ? `「${radarName}」` : "本次抓取";
  return `${target}将按已核验单价计费：本轮最多 USD ${budgets.single_run_limit_usd}，每日最多 USD ${budgets.daily_limit_usd} / ${budgets.daily_request_limit} 请求（费用以平台账单为准）。确认开始手动运行？`;
}

export function approveRun(budgets: ProviderBudgets, confirm: (message: string) => boolean = defaultConfirm, radarName?: string): boolean {
  if (!budgets.confirm_required) return true;
  return confirm(confirmMessage(budgets, radarName));
}

function defaultConfirm(message: string): boolean {
  return typeof window === "undefined" ? true : window.confirm(message);
}
