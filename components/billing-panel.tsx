"use client";
import { useCallback, useEffect, useState } from "react";
import { getAccessToken } from "@/lib/auth";
import { apiRequest } from "@/lib/api-client";
import { Button, Panel } from "@/components/ui";

type Policy = { scope: string; enabled: boolean; allow_scheduled: boolean; remaining_requests: number; remaining_cost_usd: number };
type Status = { batch?:{enabled:boolean;remaining_requests:number;remaining_cost_usd:number;actual_cost_usd:number|null;request_cost_limit_usd:number}|null; paid_api_enabled: boolean; requests_today: number; reserved_cost_usd: number; consumed_cost_usd?: number; account_remaining_requests?: number; account_remaining_cost_usd?: number; actual_cost_usd: number | null; authorizations: Policy[]; warning?: string };

export function BillingPanel({ editable = false, refreshKey = 0 }: { editable?: boolean; refreshKey?: number }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [scope, setScope] = useState("evidence");
  const [enabled, setEnabled] = useState(false);
  const [scheduled, setScheduled] = useState(false);
  const [runRequests, setRunRequests] = useState(1);
  const [dailyRequests, setDailyRequests] = useState(5);
  const [runCost, setRunCost] = useState(.1);
  const [dailyCost, setDailyCost] = useState(.5);
  const [providers, setProviders] = useState<string[]>(["tikhub", "firecrawl"]);
  const load = useCallback(async () => {
    try { const token = await getAccessToken(); if (!token) return; setStatus(await apiRequest<Status>("/api/billing/status", {}, token)); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "无法读取费用额度"); }
  }, []);
  useEffect(() => { void load(); }, [load, refreshKey]);
  async function save() {
    setBusy(true); setError("");
    try { const token = await getAccessToken(); if (!token) throw new Error("请先登录"); await apiRequest(`/api/billing/authorizations/${encodeURIComponent(scope)}`, {method:"PUT", body:JSON.stringify({enabled,providers,allow_scheduled:scheduled,run_requests:runRequests,daily_requests:dailyRequests,run_cost_usd:runCost,daily_cost_usd:dailyCost})}, token); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : "授权保存失败"); }
    finally { setBusy(false); }
  }
  return <Panel className="mb-4 p-4">
    <div className="flex flex-wrap justify-between gap-3"><h2 className="font-semibold">付费采集与 AI 额度</h2><Button variant="secondary" onClick={() => void load()}>刷新</Button></div>
    <p className="mt-2 text-sm text-amber-200">{status ? (status.paid_api_enabled ? "服务器允许付费，所有调用仍需下方范围授权。" : "真实付费调用已关闭。服务器管理员启用前，授权配置不会发起付费请求。") : "额度尚未加载"}</p>
    {status && <p className="mt-2 text-xs text-muted">今日请求 {status.requests_today} · 预估预留 ${status.reserved_cost_usd.toFixed(4)} · 额度占用 ${(status.consumed_cost_usd ?? status.reserved_cost_usd).toFixed(4)} · 服务商实际费用 {status.actual_cost_usd === null ? "未知" : `$${status.actual_cost_usd.toFixed(4)}`}（每日额度按 UTC 重置）</p>}
    {status?.account_remaining_requests !== undefined && <p className="mt-2 text-xs text-muted">账户剩余上限 {status.account_remaining_requests} 次 / ${status.account_remaining_cost_usd?.toFixed(4)}（仍需具体范围授权）</p>}
    {status?.warning && <p className="mt-2 text-sm text-amber-200">{status.warning}</p>}
    {status?.batch && <p className="mt-2 text-sm text-amber-100">本轮累计剩余 {status.batch.remaining_requests} 次 / ${status.batch.remaining_cost_usd.toFixed(4)} · 单请求上限 ${status.batch.request_cost_limit_usd.toFixed(2)} · {status.batch.enabled ? "批次已授权" : "批次已关闭"}（跨日和重启不恢复） · 实际费用 {status.batch.actual_cost_usd === null ? "未知" : `$${status.batch.actual_cost_usd.toFixed(4)}`}</p>}
    {status?.authorizations.map(p => <p key={p.scope} className="mt-2 text-xs text-muted">{p.scope} · {p.enabled ? "已授权" : "已关闭"} · 剩余 {p.remaining_requests} 次 / ${p.remaining_cost_usd.toFixed(4)} · 定时 {p.allow_scheduled ? "允许" : "禁止"}</p>)}
    {editable && <div className="mt-4 space-y-3 border-t border-line pt-4 text-sm">
      <label className="block">授权范围（evidence / assistant / Radar ID）<input aria-label="授权范围" className="ml-2 rounded border border-line bg-ink p-2" value={scope} onChange={e => setScope(e.target.value)} /></label>
      <div className="flex flex-wrap gap-4">{["tikhub", "firecrawl", "llm", "embedding"].map(provider => <label key={provider}><input type="checkbox" checked={providers.includes(provider)} onChange={e => setProviders(e.target.checked ? [...providers, provider] : providers.filter(x => x !== provider))} /> {provider}</label>)}</div>
      <div className="grid gap-3 sm:grid-cols-2">{[["单次请求上限",runRequests,setRunRequests],["每日请求上限",dailyRequests,setDailyRequests],["单次费用上限 USD",runCost,setRunCost],["每日费用上限 USD",dailyCost,setDailyCost]].map(([label,value,setter]) => <label key={String(label)}>{String(label)}<input aria-label={String(label)} className="ml-2 w-24 rounded border border-line bg-ink p-2" type="number" min="0.0001" step="any" value={Number(value)} onChange={e => (setter as (v:number)=>void)(Number(e.target.value))} /></label>)}</div>
      <label className="block"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> 我明确授权上述来源在额度内产生费用</label>
      <label className="block"><input type="checkbox" checked={scheduled} onChange={e => setScheduled(e.target.checked)} /> 允许此范围的定时付费调用</label>
      <Button disabled={busy || !scope.trim()} onClick={() => void save()}>{busy ? "保存中…" : "保存授权与额度"}</Button>
    </div>}
    {error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}
  </Panel>;
}
