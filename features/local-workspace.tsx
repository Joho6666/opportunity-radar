"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowRight, CircleAlert, CircleCheck, Loader2, Plus, RefreshCw, Settings2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, EmptyState, PageHeader, Panel } from "@/components/ui";
import { CollectionControls } from "@/components/collection-controls";
import { DEFAULT_COLLECTION_POLICY, splitTerms, validPolicy, type CollectionPolicy } from "@/lib/collection-policy";
import { formatLocalDate, localRequest } from "@/lib/local-edition";

type Radar = { id: string; name: string; goal: string; mode: "general" | "acquisition"; status: string; sources: string[]; source_config: Record<string, string>; keywords: string[]; frequency: string; freshness_hours: number; local_schedule_enabled: boolean; last_run_at: string | null; next_run_at: string | null; stats: { items_found: number; analyzed: number; duplicates_removed: number } };
type Run = { id: string; radar_id: string; status: "queued" | "running" | "completed" | "failed"; error_message?: string | null; error_code?: string | null; started_at?: string | null; finished_at?: string | null; stats?: { items_found?: number; analyzed?: number; duplicates_removed?: number } };
type Overview = { radars: Radar[]; runs: Run[] };
const freeSources = [{ id: "github", name: "GitHub 开源项目", detail: "公开项目与更新" }, { id: "hackernews", name: "Hacker News", detail: "公开技术讨论" }, { id: "rss", name: "RSS 订阅", detail: "你提供的公开订阅地址" }];

export function LocalRadars() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const load = useCallback(async () => {
    setError("");
    try { setOverview(await localRequest<Overview>("/api/local/overview")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "雷达列表暂不可用。"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setSelectedId(new URLSearchParams(window.location.search).get("selected") ?? ""); }, []);
  const activeRun = overview?.runs.find(run => run.status === "queued" || run.status === "running");
  const activeRunId = activeRun?.id ?? "";
  const activeRunStatus = activeRun?.status ?? "";
  useEffect(() => { if (!activeRunId) return; const timer = setTimeout(() => void load(), activeRunStatus === "running" ? 4000 : 6000); return () => clearTimeout(timer); }, [activeRunId, activeRunStatus, load]);
  async function run(id: string) {
    setError("");
    try { await localRequest<Run>(`/api/radars/${encodeURIComponent(id)}/run`, { method: "POST", body: "{}" }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "提交运行失败。"); }
  }
  const selected = overview?.radars.find(item => item.id === selectedId);
  return <AppShell><PageHeader title="我的雷达" description="通用主题雷达默认手动运行，只采集你选定的免费公开来源。" action={<Link href="/radars/new"><Button><Plus size={16}/>创建雷达</Button></Link>}/>
    {error && <Panel role="alert" className="mb-4 border-red-200 p-3"><div className="flex items-center justify-between gap-3 text-sm text-red-800"><span>{error}</span><Button variant="secondary" onClick={() => void load()}><RefreshCw size={14}/>重试</Button></div></Panel>}
    {loading && !overview ? <Panel className="flex items-center gap-2 p-8 text-sm text-muted"><Loader2 className="animate-spin" size={17}/>读取雷达…</Panel> : overview && !overview.radars.length ? <EmptyState title="还没有关注主题"><p className="text-sm text-muted">先填写一个主题并选择来源。不会自动附加有偿、地区或找客户条件。</p><Link href="/radars/new"><Button className="mt-4">创建第一个雷达</Button></Link></EmptyState> : overview && <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,.8fr)]">
      <div className="divide-y divide-line rounded-lg border border-line bg-white">{overview.radars.map(radar => { const recentRun = overview.runs.find(runItem => runItem.radar_id === radar.id); const active = recentRun?.status === "queued" || recentRun?.status === "running"; return <div key={radar.id} className={`p-4 ${selected?.id === radar.id ? "bg-indigo-50/50" : ""}`}><div className="flex flex-wrap items-start justify-between gap-3"><button type="button" className="min-w-0 flex-1 text-left" onClick={() => { const params = new URLSearchParams(window.location.search); params.set("selected", radar.id); history.replaceState(null, "", `/radars?${params}`); setSelectedId(radar.id); }}><span className="font-semibold">{radar.name}</span><span className="mt-1 block text-sm text-muted">{radar.goal}</span></button><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-muted">{radar.mode === "general" ? "通用情报" : "获客模式"} · {radar.status}</span></div><div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted">{radar.sources.map(source => freeSources.find(item => item.id === source)?.name ?? source).join("、")} · 上次运行 {formatLocalDate(radar.last_run_at)}</p><Button variant="secondary" disabled={active} onClick={() => void run(radar.id)}><RefreshCw size={14}/>{active ? "运行中" : "手动运行"}</Button></div>{recentRun && <p className={`mt-2 text-xs ${recentRun.status === "failed" ? "text-red-800" : "text-muted"}`}>{recentRun.status === "completed" ? `完成 · 采集 ${recentRun.stats?.items_found ?? 0} 条 · 保存情报 ${recentRun.stats?.analyzed ?? 0} 条 · 去重 ${recentRun.stats?.duplicates_removed ?? 0} 条` : recentRun.status === "failed" ? `${recentRun.error_code ?? "运行失败"} · ${recentRun.error_message ?? "请查看运行记录"}` : `${recentRun.status === "queued" ? "等待派发" : "正在运行"} · ${formatLocalDate(recentRun.started_at)}`}</p>}</div>; })}</div>
      <Panel className="p-5">{selected ? <><div className="flex items-center justify-between gap-2"><h2 className="font-semibold">{selected.name}</h2><Link href={`/evidence?radar_id=${encodeURIComponent(selected.id)}`} className="inline-flex items-center gap-1 text-sm text-ai">查看情报 <ArrowRight size={14}/></Link></div><p className="mt-2 text-sm leading-6 text-muted">{selected.goal}</p><dl className="mt-5 space-y-3 border-t border-line pt-4 text-sm"><div><dt className="text-xs text-muted">来源</dt><dd className="mt-1">{selected.sources.join("、")}</dd></div><div><dt className="text-xs text-muted">主题词</dt><dd className="mt-1">{selected.keywords.join("、") || "使用完整关注主题"}</dd></div><div><dt className="text-xs text-muted">采集频率</dt><dd className="mt-1">{selected.local_schedule_enabled ? selected.frequency : "手动运行"}</dd></div><div><dt className="text-xs text-muted">时间窗口</dt><dd className="mt-1">{selected.freshness_hours} 小时</dd></div></dl><p className="mt-5 text-xs leading-5 text-muted">相关度使用可解释规则排序；买方分数、公开热度和成交预测不会合并。</p></> : <div className="py-8 text-sm text-muted"><Settings2 size={18} className="mb-2 text-muted"/><p>选择一个雷达查看配置与最近运行。</p></div>}</Panel>
    </div>}
  </AppShell>;
}

export function LocalRadarDetail() {
  const { id } = useParams<{ id: string }>();
  const [radar, setRadar] = useState<Radar | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setError("");
    try {
      const [nextRadar, overview] = await Promise.all([localRequest<Radar>(`/api/radars/${encodeURIComponent(id)}`), localRequest<Overview>("/api/local/overview")]);
      setRadar(nextRadar); setRuns(overview.runs.filter(run => run.radar_id === id));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "雷达暂不可用。"); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  const active = runs.find(run => run.status === "queued" || run.status === "running");
  const activeId = active?.id ?? "";
  const activeStatus = active?.status ?? "";
  useEffect(() => { if (!activeId) return; const timer = setTimeout(() => void load(), activeStatus === "running" ? 4000 : 6000); return () => clearTimeout(timer); }, [activeId, activeStatus, load]);
  async function runNow() {
    setBusy(true); setError("");
    try { await localRequest<Run>(`/api/radars/${encodeURIComponent(id)}/run`, { method: "POST", body: "{}" }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "提交运行失败。"); }
    finally { setBusy(false); }
  }
  async function setPaused(paused: boolean) {
    setBusy(true); setError("");
    try { await localRequest(`/api/radars/${encodeURIComponent(id)}/${paused ? "pause" : "resume"}`, { method: "POST", body: "{}" }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "更新雷达状态失败。"); }
    finally { setBusy(false); }
  }
  return <AppShell><PageHeader title={radar?.name ?? (loading ? "读取雷达…" : "雷达不存在")} description={radar?.goal} action={<div className="flex flex-wrap gap-2"><Link href="/radars"><Button variant="secondary">返回雷达</Button></Link>{radar && <Button variant="secondary" disabled={busy} onClick={() => void setPaused(radar.status !== "paused")}>{radar.status === "paused" ? "恢复" : "暂停"}</Button>}<Button disabled={!radar || busy || !!active || radar.status === "paused"} onClick={() => void runNow()}><RefreshCw size={15}/>{active ? "运行中" : "立即运行"}</Button></div>}/>
    {error && <Panel className="mb-4 border-red-200 p-3" role="alert"><div className="flex items-center justify-between gap-2 text-sm text-red-800"><span>{error}</span><Button variant="secondary" onClick={() => void load()}>重试</Button></div></Panel>}
    {loading && !radar ? <Panel className="flex items-center gap-2 p-8 text-sm text-muted"><Loader2 size={16} className="animate-spin"/>读取配置…</Panel> : radar && <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(300px,.8fr)]">
      <Panel className="p-5"><div className="flex flex-wrap gap-2 text-xs text-muted"><span className="rounded bg-slate-100 px-2 py-1">{radar.mode === "general" ? "通用情报" : "获客模式"}</span><span>状态：{radar.status}</span><span>频率：{radar.local_schedule_enabled ? radar.frequency : "手动"}</span></div><p className="mt-4 text-sm leading-6">{radar.goal}</p><dl className="mt-5 space-y-4 border-t border-line pt-4 text-sm"><div><dt className="text-xs text-muted">来源</dt><dd className="mt-1">{radar.sources.join("、")}</dd></div><div><dt className="text-xs text-muted">主题词</dt><dd className="mt-1">{radar.keywords.join("、") || "使用完整关注主题"}</dd></div><div><dt className="text-xs text-muted">RSS 地址</dt><dd className="mt-1 break-all">{radar.source_config?.rss_feed_url || "未设置"}</dd></div><div><dt className="text-xs text-muted">最近运行</dt><dd className="mt-1">{formatLocalDate(radar.last_run_at)}</dd></div><div><dt className="text-xs text-muted">最近运行数量</dt><dd className="mt-1">采集 {radar.stats?.items_found ?? 0} 条 · 保存 {radar.stats?.analyzed ?? 0} 条 · 重复 {radar.stats?.duplicates_removed ?? 0} 条</dd></div></dl><p className="mt-5 text-xs leading-5 text-muted">通用相关度用于排序，不是买方概率。暂停只阻止后续运行，不删除已有情报。</p><Link href={`/evidence?radar_id=${encodeURIComponent(radar.id)}`} className="mt-5 inline-flex min-h-11 items-center text-sm text-ai underline">查看该主题的情报</Link></Panel>
      <Panel className="p-5"><h2 className="font-semibold">运行历史</h2>{runs.length ? <div className="mt-3 divide-y divide-line">{runs.slice(0, 8).map(run => <div key={run.id} className="py-3 first:pt-0 last:pb-0"><p className="text-sm">{run.status === "completed" ? <CircleCheck size={14} className="mr-1 inline text-emerald-700"/> : run.status === "failed" ? <CircleAlert size={14} className="mr-1 inline text-red-700"/> : <Loader2 size={14} className="mr-1 inline animate-spin text-muted"/>}{run.status} · {formatLocalDate(run.finished_at ?? run.started_at)}</p>{run.error_message && <p className="mt-1 text-xs text-red-800">{run.error_code ? `${run.error_code} · ` : ""}{run.error_message}</p>}{run.status === "completed" && <p className="mt-1 text-xs text-muted">采集 {run.stats?.items_found ?? 0} · 保存 {run.stats?.analyzed ?? 0} · 去重 {run.stats?.duplicates_removed ?? 0}</p>}</div>)}</div> : <p className="mt-4 text-sm text-muted">暂无运行记录。</p>}</Panel>
    </div>}
  </AppShell>;
}

export function LocalNewRadar() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [theme, setTheme] = useState("");
  const [sources, setSources] = useState<string[]>(["hackernews"]);
  const [advanced, setAdvanced] = useState(false);
  const [keywords, setKeywords] = useState("");
  const [feedUrl, setFeedUrl] = useState("");
  const [hours, setHours] = useState(168);
  const [policy, setPolicy] = useState<CollectionPolicy>(DEFAULT_COLLECTION_POLICY);
  const [scheduled, setScheduled] = useState(false);
  const [frequency, setFrequency] = useState("daily");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function toggleSource(id: string) { setSources(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]); }
  async function submit() {
    setBusy(true); setError("");
    try {
      const terms = splitTerms(keywords);
      const effectivePolicy = sources.includes("rss") && feedUrl.trim() && terms.length && !policy.required_terms.length ? { ...policy, required_terms: terms, match_mode: "any" as const } : policy;
      await localRequest("/api/radars", { method: "POST", body: JSON.stringify({ name: name.trim(), goal: theme.trim(), mode: "general", minimum_budget: 0, frequency: scheduled ? frequency : "manual", local_schedule_enabled: scheduled, freshness_hours: hours, collection_policy: effectivePolicy, keywords: terms, locations: [], sources, source_config: feedUrl.trim() ? { rss_feed_url: feedUrl.trim() } : {}, listener_description: "" }) });
      router.push("/radars");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存雷达失败。"); }
    finally { setBusy(false); }
  }
  const canSave = name.trim().length > 0 && theme.trim().length > 0 && sources.length > 0 && Number.isInteger(hours) && hours >= 1 && hours <= 720 && validPolicy(policy);
  return <AppShell><PageHeader title="新建关注主题" description="描述你想持续了解的内容，再选择公开来源。"/>
    <Panel className="max-w-3xl p-5">
      <div className="grid gap-4 sm:grid-cols-2"><label className="text-sm"><span className="mb-1 block text-muted">名称</span><input autoFocus value={name} onChange={event => setName(event.target.value)} placeholder="例如：开源 AI Agent" className="h-11 w-full rounded-md border border-line bg-white px-3"/></label><label className="text-sm"><span className="mb-1 block text-muted">关注主题</span><input value={theme} onChange={event => setTheme(event.target.value)} placeholder="例如：本地运行的多模态 Agent 项目" className="h-11 w-full rounded-md border border-line bg-white px-3"/></label></div>
      <fieldset className="mt-6"><legend className="text-sm font-medium">公开来源</legend><div className="mt-2 grid gap-2 sm:grid-cols-3">{freeSources.map(item => <label key={item.id} className={`flex min-h-16 cursor-pointer items-start gap-3 rounded-md border p-3 ${sources.includes(item.id) ? "border-indigo-300 bg-indigo-50/50" : "border-line"}`}><input type="checkbox" checked={sources.includes(item.id)} onChange={() => toggleSource(item.id)} className="mt-1"/><span><span className="block text-sm font-medium">{item.name}</span><span className="mt-1 block text-xs text-muted">{item.detail}</span></span></label>)}</div></fieldset>
      {sources.includes("rss") && <label className="mt-4 block text-sm"><span className="mb-1 block text-muted">RSS 订阅地址（可选）</span><input type="url" value={feedUrl} onChange={event => setFeedUrl(event.target.value)} placeholder="https://example.com/feed.xml" className="h-11 w-full rounded-md border border-line bg-white px-3"/><span className="mt-1 block text-xs text-muted">会校验公网地址；填入后按高级设置中的主题词筛选订阅内容。</span></label>}
      <div className="mt-5 border-t border-line pt-4"><button type="button" aria-expanded={advanced} onClick={() => setAdvanced(open => !open)} className="inline-flex min-h-11 items-center gap-2 text-sm font-medium"><Settings2 size={16}/>高级设置</button>{advanced && <div className="mt-4 space-y-4"><label className="block text-sm"><span className="mb-1 block text-muted">关键词（可选，逗号分隔）</span><input value={keywords} onChange={event => setKeywords(event.target.value)} placeholder="留空时使用关注主题" className="h-11 w-full rounded-md border border-line bg-white px-3"/></label><label className="block text-sm"><span className="mb-1 block text-muted">时间窗口</span><select value={hours} onChange={event => setHours(Number(event.target.value))} className="h-11 rounded-md border border-line bg-white px-3"><option value={24}>最近 24 小时</option><option value={72}>最近 3 天</option><option value={168}>最近 7 天</option><option value={720}>最近 30 天</option></select></label><CollectionControls policy={policy} onChange={setPolicy} hours={hours} onHours={setHours} disabled={busy}/><label className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={scheduled} onChange={event => setScheduled(event.target.checked)}/>启用定时运行</label>{scheduled && <select value={frequency} onChange={event => setFrequency(event.target.value)} className="h-11 rounded-md border border-line bg-white px-3"><option value="daily">每天</option><option value="weekly">每周</option><option value="hourly">每小时</option></select>}<p className="text-xs leading-5 text-muted">定时任务只使用当前已选择的免费来源。收费来源、自动 AI 和数据删除在 Local Edition 中默认关闭。</p></div>}</div>
      {error && <p role="alert" className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      <div className="mt-5 flex justify-end gap-2"><Link href="/radars"><Button variant="secondary">取消</Button></Link><Button disabled={!canSave || busy} onClick={() => void submit()}>{busy ? <><Loader2 className="animate-spin" size={15}/>保存中</> : "保存雷达"}</Button></div>
    </Panel>
  </AppShell>;
}

export function LocalSettings() {
  const [mode, setMode] = useState<"off" | "on_demand">("off");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { void localRequest<{ ai_mode: "off" | "on_demand"; ai_reason?: string }>("/api/local/settings").then(value => { setMode(value.ai_mode); setReason(value.ai_reason ?? ""); }).catch(reason => setError(reason instanceof Error ? reason.message : "设置暂不可用。" )).finally(() => setLoading(false)); }, []);
  async function save(value: "off" | "on_demand") {
    setBusy(true); setError("");
    try { const result = await localRequest<{ ai_mode: "off" | "on_demand"; ai_reason?: string }>("/api/local/settings", { method: "PUT", body: JSON.stringify({ ai_mode: value }) }); setMode(result.ai_mode); setReason(result.ai_reason ?? ""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "设置保存失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <AppShell><PageHeader title="设置" description="Local Edition 默认关闭付费调用、自动 AI 和保留期清理。"/>
    {error && <Panel role="alert" className="mb-4 border-red-200 p-3"><p className="text-sm text-red-800">{error}</p></Panel>}
    <div className="max-w-3xl space-y-7"><section><h2 className="mb-3 font-semibold">分析方式</h2><Panel className="p-5"><p className="text-sm text-muted">自动采集只使用规则筛选与可解释排序。按需模式仅在你点击单条信息的分析按钮时尝试模型；未配置或未授权时回退到现有规则结果。</p><div className="mt-4 flex flex-wrap gap-2"><Button variant={mode === "off" ? "primary" : "secondary"} disabled={loading || busy} onClick={() => void save("off")}>关闭 AI</Button><Button variant={mode === "on_demand" ? "primary" : "secondary"} disabled={loading || busy} onClick={() => void save("on_demand")}>按需分析</Button></div>{reason && <p className="mt-3 text-xs text-amber-900">{reason}</p>}{loading && <p className="mt-3 text-xs text-muted">读取设置…</p>}</Panel></section>
      <section><h2 className="mb-3 font-semibold">费用与数据</h2><Panel className="divide-y divide-line"><p className="py-3 text-sm first:pt-0"><span className="font-medium">付费 API</span><span className="ml-3 text-muted">关闭</span></p><p className="py-3 text-sm"><span className="font-medium">自动分类模型</span><span className="ml-3 text-muted">关闭</span></p><p className="py-3 text-sm"><span className="font-medium">本地分类器</span><span className="ml-3 text-muted">关闭</span></p><p className="py-3 text-sm last:pb-0"><span className="font-medium">自动删除历史记录</span><span className="ml-3 text-muted">关闭</span></p><p className="mt-3 text-xs leading-5 text-muted">所有业务数据写入独立 PostgreSQL 数据库；备份与恢复由本机脚本管理。</p></Panel></section>
      <section><h2 className="mb-3 font-semibold">运行模式</h2><Panel className="p-5"><p className="flex items-center gap-2 text-sm"><CircleCheck size={16} className="text-emerald-700"/>本机单用户 · PostgreSQL 持久化 · Redis 后台队列</p><p className="mt-2 text-xs text-muted">服务绑定 loopback；Next.js 通过同源代理访问 FastAPI。需要远程访问时请使用受保护的私有网络与额外访问控制。</p></Panel></section>
    </div>
  </AppShell>;
}
