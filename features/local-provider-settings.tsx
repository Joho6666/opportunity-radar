"use client";

import { useCallback, useEffect, useState } from "react";
import { CircleAlert, CircleCheck, Loader2, ShieldCheck } from "lucide-react";
import { Button, Panel } from "@/components/ui";
import { localRequest } from "@/lib/local-edition";
import { LOCAL_LIMITS, readBudgets, type ProviderBudgets, type ProviderConfigResponse, type ProviderPlaceholder, type ProviderTestResult, type TikHubProviderState } from "@/lib/local-providers";

const KEY_SOURCE_LABELS: Record<TikHubProviderState["key_source"], string> = { ui: "界面保存（本机私密配置 0600）", env: "local.env（旧配置，保存或删除后以界面为准）", none: "未配置" };
const field = "mt-1 h-11 w-full rounded border border-line px-3 text-sm";

/** 界面内 API 配置：TikHub 密钥（掩码显示）、测试连接、预算与限额。 */
export function LocalProviderSection() {
  const [state, setState] = useState<TikHubProviderState | null>(null);
  const [placeholders, setPlaceholders] = useState<ProviderPlaceholder[]>([]);
  const [budget, setBudget] = useState<ProviderBudgets>(readBudgets({}));
  const [keyInput, setKeyInput] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);

  const apply = useCallback((data: ProviderConfigResponse) => { setState(data.tikhub); setPlaceholders(data.placeholders); setBudget(readBudgets(data.tikhub.budgets)); }, []);
  const load = useCallback(async () => {
    setError("");
    try { apply(await localRequest<ProviderConfigResponse>("/api/local/providers")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Provider 配置暂不可用。"); }
  }, [apply]);
  useEffect(() => { void load(); }, [load]);

  async function run(action: string, work: () => Promise<void>) {
    setBusy(action); setError("");
    try { await work(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败，请重试。"); }
    finally { setBusy(""); }
  }

  async function saveKey() {
    const value = keyInput.trim();
    if (!value) { setError("请先输入 API Key。"); return; }
    await run("key", async () => {
      const data = await localRequest<{ tikhub: TikHubProviderState }>("/api/local/providers/tikhub", { method: "PUT", body: JSON.stringify({ api_key: value, enabled: true }) });
      setState(data.tikhub); setKeyInput(""); setTestResult(null);
      setNotice("密钥已保存到本机私密配置（目录 700 / 文件 600）；页面只显示掩码，保存后立即生效，无需重启服务。");
    });
  }
  async function deleteKey() {
    if (typeof window !== "undefined" && !window.confirm("删除本机保存的 TikHub 密钥？local.env 中的旧密钥也会同时被屏蔽。")) return;
    await run("delete", async () => {
      const data = await localRequest<{ tikhub: TikHubProviderState }>("/api/local/providers/tikhub", { method: "DELETE" });
      setState(data.tikhub); setTestResult(null); setNotice("已删除本机密钥；TikHub 手动采集停用，local.env 中的旧密钥同样被屏蔽。");
    });
  }
  async function testKey() {
    await run("test", async () => {
      const result = await localRequest<ProviderTestResult & { masked_key: string; persisted: boolean }>("/api/local/providers/tikhub/test", { method: "POST", body: "{}" });
      setTestResult(result);
      setNotice(`测试连接：${result.message} HTTP ${result.http_status ?? "-"} · ${result.latency_ms}ms · 掩码 ${result.masked_key}${result.persisted ? " · 已记录到本机配置" : ""}`);
      await load();
    });
  }
  async function saveBudget() {
    await run("budget", async () => {
      const data = await localRequest<{ tikhub: TikHubProviderState }>("/api/local/providers/tikhub/budget", { method: "PUT", body: JSON.stringify(budget) });
      setState(data.tikhub); setBudget(readBudgets(data.tikhub.budgets)); setNotice("预算已保存并立即生效：计费网关的预留、账本与授权机制保持不变。");
    });
  }

  return <Panel className="space-y-6 p-5">
    <p className="text-sm leading-6 text-muted">密钥只写入本机私密配置（应用数据目录的 config 子目录，目录 700 / 文件 600），接口与页面只显示掩码，绝不回传明文；测试连接仅调用 TikHub 官方用户信息端点，不发起内容采集。保存后立刻生效，无需重启服务。</p>
    {error && <p role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {notice && <p className="rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{notice}</p>}

    <section>
      <h3 className="text-sm font-medium">TikHub API Key</h3>
      {!state && !error && <p className="mt-2 flex items-center gap-2 text-sm text-muted"><Loader2 size={15} className="animate-spin"/>读取配置…</p>}
      {state && <>
        <div className="mt-2 rounded-md bg-slate-50 p-3 text-sm leading-6">
          <p className="flex flex-wrap items-center gap-2"><span className={state.enabled ? "inline-flex items-center gap-1 text-emerald-700" : "inline-flex items-center gap-1 text-muted"}>{state.enabled ? <CircleCheck size={15}/> : <CircleAlert size={15}/>}{state.enabled ? "手动采集已启用" : state.configured ? "已保存但停用" : "未配置密钥"}</span><span className="text-muted">掩码：<span className="mono">{state.masked_key || "—"}</span> · 来源：{KEY_SOURCE_LABELS[state.key_source]}</span></p>
          {(testResult ?? state.last_test) && <p className="mt-1 text-xs text-muted">最近测试：{(testResult ?? state.last_test)!.message}（HTTP {(testResult ?? state.last_test)!.http_status ?? "-"} · {(testResult ?? state.last_test)!.latency_ms}ms · {(testResult ?? state.last_test)!.tested_at}）</p>}
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
          <label className="text-sm">输入新密钥（替换已有密钥）<input type="password" autoComplete="off" aria-label="TikHub API Key" value={keyInput} onChange={e => setKeyInput(e.target.value)} placeholder="sk-…" className={field}/></label>
          <div className="flex items-end gap-2"><Button disabled={!!busy} onClick={() => void saveKey()}>{busy === "key" ? "保存中…" : "保存密钥"}</Button><Button variant="secondary" disabled={!!busy || !state.configured} onClick={() => void testKey()}>{busy === "test" ? "测试中…" : "测试连接"}</Button>{state.configured && <Button variant="secondary" disabled={!!busy} onClick={() => void deleteKey()}>删除密钥</Button>}</div>
        </div>
        <p className="mt-2 text-xs text-muted">保存页面上永远不会显示明文：保存后输入框即清空，只保留掩码与状态。删除后 local.env 里的旧密钥也不会再生效。</p>
      </>}
    </section>

    <section>
      <h3 className="text-sm font-medium">预算与限额（本机硬上限：单轮/每日 ≤ USD {LOCAL_LIMITS.daily_limit_usd}，每日 ≤ {LOCAL_LIMITS.daily_request_limit} 请求）</h3>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">
        <label className="text-sm">单轮上限（USD）<input type="number" min={0.01} max={LOCAL_LIMITS.single_run_limit_usd} step={0.01} aria-label="单轮上限" value={budget.single_run_limit_usd} onChange={e => setBudget(current => ({ ...current, single_run_limit_usd: Number(e.target.value) }))} className={field}/></label>
        <label className="text-sm">每日上限（USD）<input type="number" min={0.01} max={LOCAL_LIMITS.daily_limit_usd} step={0.01} aria-label="每日费用上限" value={budget.daily_limit_usd} onChange={e => setBudget(current => ({ ...current, daily_limit_usd: Number(e.target.value) }))} className={field}/></label>
        <label className="text-sm">每日请求上限<input type="number" min={1} max={LOCAL_LIMITS.daily_request_limit} step={1} aria-label="每日请求上限" value={budget.daily_request_limit} onChange={e => setBudget(current => ({ ...current, daily_request_limit: Number(e.target.value) }))} className={field}/></label>
        <label className="flex items-end gap-2 text-sm"><input type="checkbox" checked={budget.confirm_required} onChange={e => setBudget(current => ({ ...current, confirm_required: e.target.checked }))} className="mb-3"/>每次手动运行前弹出确认（推荐）</label>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3"><p className="text-xs text-muted">默认：单轮 USD 0.10 · 每日 USD 1 / 20 请求。上限不能超过本机硬上限；超限会被服务端拒绝。</p><Button variant="secondary" disabled={!!busy} onClick={() => void saveBudget()}>{busy === "budget" ? "保存中…" : "保存预算"}</Button></div>
    </section>

    <section>
      <h3 className="inline-flex items-center gap-2 text-sm font-medium"><ShieldCheck size={15} className="text-emerald-700"/>其他 Provider</h3>
      <div className="mt-2 space-y-2">{placeholders.map(item => <div key={item.id} className="rounded-md border border-line p-3 text-sm"><p className="flex flex-wrap items-center gap-2"><span className="font-medium">{item.name}</span><span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">{item.status}</span></p><p className="mt-1 text-xs leading-5 text-muted">{item.detail}</p></div>)}</div>
    </section>
  </Panel>;
}
