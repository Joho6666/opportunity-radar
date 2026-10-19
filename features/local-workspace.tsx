"use client";

import Link from "next/link";
import { runManualRadar } from "@/lib/manual-radar";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { ArrowRight, CircleAlert, CircleCheck, Loader2, Plus, RefreshCw, Settings2 } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, EmptyState, PageHeader, Panel } from "@/components/ui";
import { LocalIdentitySection } from "@/features/local-identity";
import { LocalAgentSection } from "@/features/local-agent-settings";
import { LocalProviderSection } from "@/features/local-provider-settings";
import { splitTerms } from "@/lib/collection-policy";
import { identityToRadarPrefill, type LocalIdentity } from "@/lib/identity";
import { approveRun, fetchBudgets } from "@/lib/local-providers";
import { BUSINESS_PRESETS, buildLeadRadar, isHuntSourceSelectable, HUNT_ROLES, HUNT_INTENTS, DEFAULT_HUNT_CONDITIONS, describeHuntConditions, readHuntConditions, shanghaiToUtc, utcToShanghaiInput, groupHuntSources, selectAllAvailable, estimateHunt, platformQueries, shortenDouyinKeyword, WECHAT_SCOPES, wechatScopeMeta, DEFAULT_WECHAT_SCOPE, parseTelegramChannels, parseToutiaoLinks, telegramChannelError, toutiaoLinkError, MAX_RUN_REQUESTS, type HuntConditions, type HuntSource, type WechatScope } from "@/lib/lead-hunt";
import { formatLocalDate, localRequest } from "@/lib/local-edition";

type Radar = { collection_policy?: { required_terms?: string[]; excluded_terms?: string[] }; id: string; name: string; goal: string; mode: "general" | "acquisition"; status: string; sources: string[]; source_config: Record<string, string>; keywords: string[]; frequency: string; freshness_hours: number; local_schedule_enabled: boolean; last_run_at: string | null; next_run_at: string | null; stats: { items_found: number; analyzed: number; duplicates_removed: number } };
type SourceRunStat = { source: string; requests: number; returned: number; ingested: number; queries: string[]; errors: string[] };
type RunAcceptance = { passed: boolean; selected: number; passed_sources: number; unmet_sources: string[] };
type Run = { id: string; radar_id: string; status: "queued" | "running" | "completed" | "partial" | "failed"; error_message?: string | null; error_code?: string | null; started_at?: string | null; finished_at?: string | null; stats?: { items_found?: number; analyzed?: number; duplicates_removed?: number }; stage_stats?: { source_stats?: SourceRunStat[]; acceptance?: RunAcceptance; source_override?: string; query_override?: string } };
type Overview = { radars: Radar[]; runs: Run[] };
const sourceNames: Record<string, string> = { xiaohongshu: "小红书", douyin: "抖音", weibo: "微博", zhihu: "知乎", tikhub: "TikTok", reddit: "Reddit", github: "GitHub", hackernews: "Hacker News", rss: "RSS", web_search: "网页搜索", wechat_search: "微信搜一搜", wechat_channels: "微信视频号", telegram: "Telegram", linkedin: "LinkedIn", toutiao: "今日头条", bilibili: "B站", kuaishou: "快手", lemon8: "Lemon8", pipixia: "皮皮虾", threads: "Threads", twitter: "X/Twitter", youtube: "YouTube" };

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
  useEffect(() => { if (!activeRunId) return; const timer = setInterval(() => void load(), activeRunStatus === "running" ? 4000 : 6000); return () => clearInterval(timer); }, [activeRunId, activeRunStatus, load]);
  async function run(id: string) {
    setError("");
    try {
      const radar = overview!.radars.find(r => r.id === id)!;
      const budgets = await fetchBudgets();
      if (!approveRun(budgets, message => window.confirm(message), radar.name)) return;
      await runManualRadar<Run>(radar); await load();
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "提交运行失败。"); }
  }
  const selected = overview?.radars.find(item => item.id === selectedId);
  return <AppShell><PageHeader title="抓单工作台" description="看平台、买方关键词和发布时间，手动抓取后核实原文。TikHub 按核验单价手动采集，每次最多 USD 0.10，每日最多 USD 1；自动 AI 与付费调度关闭。" action={<Link href="/radars/new"><Button><Plus size={16}/>新建抓单</Button></Link>}/>
    {error && <Panel role="alert" className="mb-4 border-red-200 p-3"><div className="flex items-center justify-between gap-3 text-sm text-red-800"><span>{error}</span><Button variant="secondary" onClick={() => void load()}><RefreshCw size={14}/>重试</Button></div></Panel>}
    {loading && !overview ? <Panel className="flex items-center gap-2 p-8 text-sm text-muted"><Loader2 className="animate-spin" size={17}/>读取雷达…</Panel> : overview && !overview.radars.length ? <EmptyState title="还没有抓单配置"><p className="text-sm text-muted">从你的业务预设开始，选择平台、修改买方关键词和发布时间。</p><Link href="/radars/new"><Button className="mt-4">新建抓单</Button></Link></EmptyState> : overview && <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,.8fr)]">
      <div className="divide-y divide-line rounded-lg border border-line bg-white">{overview.radars.map(radar => { const recentRun = overview.runs.find(runItem => runItem.radar_id === radar.id); const active = recentRun?.status === "queued" || recentRun?.status === "running"; return <div key={radar.id} className={`p-4 ${selected?.id === radar.id ? "bg-indigo-50/50" : ""}`}><div className="flex flex-wrap items-start justify-between gap-3"><button type="button" className="min-w-0 flex-1 text-left" onClick={() => { const params = new URLSearchParams(window.location.search); params.set("selected", radar.id); history.replaceState(null, "", `/radars?${params}`); setSelectedId(radar.id); }}><span className="font-semibold">{radar.name}</span><span className="mt-1 block text-sm text-muted">{radar.goal}</span></button><span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-muted">{radar.source_config?.lead_hunt === "true" ? "抓单" : "原有雷达"} · {radar.status}</span></div><div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted">{radar.sources.map(source => sourceNames[source] ?? source).join("、")} · {radar.freshness_hours} 小时内 · {radar.keywords.join("、")} · 上次 {formatLocalDate(radar.last_run_at)}</p><Button variant="secondary" disabled={active} onClick={() => void run(radar.id)}><RefreshCw size={14}/>{active ? "运行中" : "手动运行"}</Button><Link href={`/evidence?radar_id=${encodeURIComponent(radar.id)}`} className="text-sm text-ai underline">查看结果原文</Link></div>{recentRun && <p className={`mt-2 text-xs ${recentRun.status === "failed" || recentRun.status === "partial" ? "text-red-800" : "text-muted"}`}>{recentRun.status === "completed" ? `成功 · 采集 ${recentRun.stats?.items_found ?? 0} 条 · 保留原文 ${recentRun.stats?.analyzed ?? 0} 条 · 去重 ${recentRun.stats?.duplicates_removed ?? 0} 条` : recentRun.status === "partial" ? `未达标 · 平台达标 ${recentRun.stage_stats?.acceptance?.passed_sources ?? 0}/${recentRun.stage_stats?.acceptance?.selected ?? 0}${recentRun.stage_stats?.acceptance?.unmet_sources?.length ? ` · 未达标：${recentRun.stage_stats.acceptance.unmet_sources.map(source => sourceNames[source] ?? source).join("、")}` : ""}` : recentRun.status === "failed" ? `${recentRun.error_code ?? "运行失败"} · ${recentRun.error_message ?? "请查看运行记录"}` : `${recentRun.status === "queued" ? "等待派发" : "正在运行"} · ${formatLocalDate(recentRun.started_at)}`}</p>}{recentRun?.error_message && recentRun.status !== "failed" && <p role="alert" className="mt-2 text-xs text-amber-900">部分来源异常：{recentRun.error_message}</p>}</div>; })}</div>
      <Panel className="p-5">{selected ? <><div className="flex items-center justify-between gap-2"><h2 className="font-semibold">{selected.name}</h2><Link href={`/evidence?radar_id=${encodeURIComponent(selected.id)}`} className="inline-flex items-center gap-1 text-sm text-ai">查看结果 <ArrowRight size={14}/></Link></div><p className="mt-2 text-sm leading-6 text-muted">{selected.goal}</p>{selected.source_config.lead_hunt === "true" && <><Link className="mt-3 inline-block text-sm text-ai underline" href={`/radars/new?edit=${encodeURIComponent(selected.id)}`}>编辑抓单条件</Link><p className="mt-2 text-xs text-muted">{describeHuntConditions(selected.source_config)}</p></>}<dl className="mt-5 space-y-3 border-t border-line pt-4 text-sm"><div><dt className="text-xs text-muted">来源</dt><dd className="mt-1">{selected.sources.join("、")}</dd></div><div><dt className="text-xs text-muted">买方关键词</dt><dd className="mt-1">{selected.keywords.join("、") || "使用完整关注主题"}</dd></div><div><dt className="text-xs text-muted">采集频率</dt><dd className="mt-1">{selected.local_schedule_enabled ? selected.frequency : "手动运行"}</dd></div><div><dt className="text-xs text-muted">时间窗口</dt><dd className="mt-1">{selected.freshness_hours} 小时</dd></div></dl><p className="mt-5 text-xs leading-5 text-muted">原文按发布时间与业务词筛选；买方候选由规则分类，需人工核实是否仍在找人。</p></> : <div className="py-8 text-sm text-muted"><Settings2 size={18} className="mb-2 text-muted"/><p>选择一个雷达查看配置与最近运行。</p></div>}</Panel>
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
    setError(new URLSearchParams(window.location.search).get("dispatch_failed") ?? "");
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
  useEffect(() => { if (!activeId) return; const timer = setInterval(() => void load(), activeStatus === "running" ? 4000 : 6000); return () => clearInterval(timer); }, [activeId, activeStatus, load]);
  async function runNow() {
    setBusy(true); setError("");
    try {
      const budgets = await fetchBudgets();
      if (!approveRun(budgets, message => window.confirm(message), radar!.name)) return;
      await runManualRadar<Run>(radar!); await load();
    }
    catch (reason) { setError(reason instanceof Error ? reason.message : "提交运行失败。"); }
    finally { setBusy(false); }
  }
  async function setPaused(paused: boolean) {
    setBusy(true); setError("");
    try { await localRequest(`/api/radars/${encodeURIComponent(id)}/${paused ? "pause" : "resume"}`, { method: "POST", body: "{}" }); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "更新雷达状态失败。"); }
    finally { setBusy(false); }
  }
  async function rerunShort(source: string, suggested: string) {
    if (!radar) return;
    if (!window.confirm(`只重跑「${sourceNames[source] ?? source}」1 个短词「${suggested}」：将产生 1 次付费请求（约 USD 0.01，计入每轮/每日额度）。确认？`)) return;
    setBusy(true); setError("");
    try {
      await localRequest(`/api/radars/${encodeURIComponent(radar.id)}/rerun-source`, {
        method: "POST", body: JSON.stringify({ source, query: suggested, confirmed: true }) });
      await load();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "单平台重跑提交失败。"); }
    finally { setBusy(false); }
  }
  const shortWord = shortenDouyinKeyword(radar?.keywords[0] ?? "") || "找拍摄";
  const sourceStats = (run: Run) => {
    const rows = run.stage_stats?.source_stats ?? [];
    if (!rows.length) return null;
    return <div className="mt-2 space-y-2">
      <div className="overflow-x-auto"><table className="min-w-full text-left text-xs">
        <thead className="text-muted"><tr><th className="pr-3 py-1">平台</th><th className="pr-3 py-1">请求</th><th className="pr-3 py-1">返回</th><th className="pr-3 py-1">入库</th><th className="py-1">实际发出的词</th></tr></thead>
        <tbody>{rows.map(stat => <tr key={stat.source} className={stat.ingested === 0 ? "text-red-800" : ""}><td className="pr-3 py-1">{sourceNames[stat.source] ?? stat.source}</td><td className="pr-3 py-1">{stat.requests}</td><td className="pr-3 py-1">{stat.returned}</td><td className="pr-3 py-1 font-medium">{stat.ingested}</td><td className="py-1">{stat.queries.join("；")}</td></tr>)}</tbody>
      </table></div>
      {rows.filter(stat => stat.ingested === 0).map(stat => <div key={stat.source} role="alert" className="rounded border border-red-200 bg-red-50 p-2 text-xs leading-5 text-red-900">
        <p><span className="font-medium">{sourceNames[stat.source] ?? stat.source}</span> 0 条入库：{stat.errors.length ? `接口异常（${stat.errors.join(" / ")}）` : stat.source === "douyin" ? "关键词可能过长或匹配过窄，抖音长短语已实测 0 条" : "首屏无匹配或关键词过窄，可换词或放宽时间窗口"}</p>
        {stat.source === "douyin" && <Button variant="secondary" disabled={busy} onClick={() => void rerunShort("douyin", shortWord)}>改用短词「{shortWord}」重跑（仅此平台，需确认付费）</Button>}
      </div>)}
    </div>;
  };
  return <AppShell><PageHeader title={radar?.name ?? (loading ? "读取雷达…" : "雷达不存在")} description={radar?.goal} action={<div className="flex flex-wrap gap-2"><Link href="/radars"><Button variant="secondary">返回雷达</Button></Link>{radar && <Button variant="secondary" disabled={busy} onClick={() => void setPaused(radar.status !== "paused")}>{radar.status === "paused" ? "恢复" : "暂停"}</Button>}<Button disabled={!radar || busy || !!active || radar.status === "paused"} onClick={() => void runNow()}><RefreshCw size={15}/>{active ? "运行中" : "立即运行"}</Button></div>}/>
    {error && <Panel className="mb-4 border-red-200 p-3" role="alert"><div className="flex items-center justify-between gap-2 text-sm text-red-800"><span>{error}</span><Button variant="secondary" onClick={() => void load()}>重试</Button></div></Panel>}
    {loading && !radar ? <Panel className="flex items-center gap-2 p-8 text-sm text-muted"><Loader2 size={16} className="animate-spin"/>读取配置…</Panel> : radar && <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(300px,.8fr)]">
      <Panel className="p-5"><div className="flex flex-wrap gap-2 text-xs text-muted"><span className="rounded bg-slate-100 px-2 py-1">{radar.source_config?.lead_hunt === "true" ? "抓单" : "原有雷达"}</span><span>状态：{radar.status}</span><span>频率：{radar.local_schedule_enabled ? radar.frequency : "手动"}</span></div><p className="mt-4 text-sm leading-6">{radar.goal}</p>{radar.source_config.lead_hunt === "true" && <><Link className="mt-3 inline-block text-sm text-ai underline" href={`/radars/new?edit=${encodeURIComponent(radar.id)}`}>编辑抓单条件</Link><p className="mt-2 text-xs text-muted">已保存条件：{describeHuntConditions(radar.source_config)}</p></>}<dl className="mt-5 space-y-4 border-t border-line pt-4 text-sm"><div><dt className="text-xs text-muted">来源</dt><dd className="mt-1">{radar.sources.join("、")}</dd></div><div><dt className="text-xs text-muted">买方关键词</dt><dd className="mt-1">{radar.keywords.join("、") || "使用完整关注主题"}</dd></div><div><dt className="text-xs text-muted">RSS 地址</dt><dd className="mt-1 break-all">{radar.source_config?.rss_feed_url || "未设置"}</dd></div><div><dt className="text-xs text-muted">最近运行</dt><dd className="mt-1">{formatLocalDate(radar.last_run_at)}</dd></div><div><dt className="text-xs text-muted">最近运行数量</dt><dd className="mt-1">采集 {radar.stats?.items_found ?? 0} 条 · 保存 {radar.stats?.analyzed ?? 0} 条 · 重复 {radar.stats?.duplicates_removed ?? 0} 条</dd></div></dl><p className="mt-5 text-xs leading-5 text-muted">点击立即运行即授权 TikHub 手动采集，每轮最多 USD 0.10，每日最多 USD 1 / 20 请求；不授权自动调度。通用相关度用于排序，不是买方概率。暂停只阻止后续运行，不删除已有情报。</p><Link href={`/evidence?radar_id=${encodeURIComponent(radar.id)}`} className="mt-5 inline-flex min-h-11 items-center text-sm text-ai underline">查看买方候选与结果原文</Link></Panel>
      <Panel className="p-5"><h2 className="font-semibold">运行历史</h2>{runs.length ? <div className="mt-3 divide-y divide-line">{runs.slice(0, 8).map(run => { const acceptance = run.stage_stats?.acceptance; const unmet = run.status === "partial" || acceptance?.passed === false; return <div key={run.id} className="py-3 first:pt-0 last:pb-0"><p className={`text-sm ${unmet ? "text-red-800" : ""}`}>{run.status === "completed" ? <CircleCheck size={14} className="mr-1 inline text-emerald-700"/> : run.status === "partial" ? <CircleAlert size={14} className="mr-1 inline text-red-700"/> : run.status === "failed" ? <CircleAlert size={14} className="mr-1 inline text-red-700"/> : <Loader2 size={14} className="mr-1 inline animate-spin text-muted"/>}{run.status === "completed" ? "成功" : run.status === "partial" ? "未达标" : run.status === "failed" ? "失败" : run.status === "queued" ? "等待派发" : "运行中"} · {formatLocalDate(run.finished_at ?? run.started_at)}</p>{acceptance && <p className={`mt-1 text-xs font-medium ${acceptance.passed ? "text-emerald-700" : "text-red-800"}`}>平台达标 {acceptance.passed_sources}/{acceptance.selected}{acceptance.unmet_sources.length ? ` · 未达标：${acceptance.unmet_sources.map(source => sourceNames[source] ?? source).join("、")}` : ""}</p>}{run.error_message && <p className="mt-1 text-xs text-red-800">{run.error_code ? `${run.error_code} · ` : ""}{run.error_message}</p>}{run.status !== "queued" && run.status !== "running" && <p className="mt-1 text-xs text-muted">采集 {run.stats?.items_found ?? 0} · 保存 {run.stats?.analyzed ?? 0} · 去重 {run.stats?.duplicates_removed ?? 0}</p>}{sourceStats(run)}</div>; })}</div> : <p className="mt-4 text-sm text-muted">暂无运行记录。</p>}</Panel>
    </div>}
  </AppShell>;
}

export function LocalNewRadar() {
  const router = useRouter();
  const [presetId, setPresetId] = useState(BUSINESS_PRESETS[0].id);
  const preset = BUSINESS_PRESETS.find(item => item.id === presetId) ?? BUSINESS_PRESETS[0];
  const [keywords, setKeywords] = useState(BUSINESS_PRESETS[0].keywords);
  const [businessTerms, setBusinessTerms] = useState(BUSINESS_PRESETS[0].terms.join("，"));
  const [sources, setSources] = useState<string[]>(["xiaohongshu"]);
  const [catalog, setCatalog] = useState<HuntSource[]>([]);
  const [feedUrl, setFeedUrl] = useState("");
  const [radarName, setRadarName] = useState("");
  const [hours, setHours] = useState(168);
  const [conditions, setConditions] = useState<HuntConditions>(DEFAULT_HUNT_CONDITIONS);
  const [regionInput, setRegionInput] = useState("");
  const [excludeTerms, setExcludeTerms] = useState("");
  const [wechatScope, setWechatScope] = useState<WechatScope>(DEFAULT_WECHAT_SCOPE);
  const [remaining, setRemaining] = useState<{ requests?: number; costUsd?: number }>({});
  const [showUnavailable, setShowUnavailable] = useState(false);
  const [identityPrefill, setIdentityPrefill] = useState<LocalIdentity | null>(null);
  const [prefillApplied, setPrefillApplied] = useState(false);
  const [customTime, setCustomTime] = useState(false);
  const [startInput, setStartInput] = useState("");
  const [endInput, setEndInput] = useState("");
  const [editing, setEditing] = useState<Radar | null>(null);
  const [editLoading, setEditLoading] = useState(false);
  const [wechatShareCount, setWechatShareCount] = useState(1);
  const [telegramChannels, setTelegramChannels] = useState("");
  const [toutiaoLinks, setToutiaoLinks] = useState("");
  useEffect(() => {
    const editId = new URLSearchParams(window.location.search).get("edit");
    if (!editId) return;
    setEditLoading(true);
    void localRequest<Radar>(`/api/radars/${encodeURIComponent(editId)}`).then(r => {
      if (r.source_config.lead_hunt !== "true") throw new Error("原有雷达不在此转换，请保留原配置。");
      setEditing(r); setPresetId(r.source_config.business || BUSINESS_PRESETS[0].id); setSources(r.sources); setKeywords(r.keywords.join("，")); setBusinessTerms((r.collection_policy?.required_terms ?? []).join("，")); setExcludeTerms((r.collection_policy?.excluded_terms ?? []).join("，")); setHours(r.freshness_hours); setFeedUrl(r.source_config.rss_feed_url || ""); setWechatScope((r.source_config.wechat_business_type as WechatScope) || DEFAULT_WECHAT_SCOPE);
      setWechatShareCount([1, 2, 3].includes(Number(r.source_config.wechat_share_links)) ? Number(r.source_config.wechat_share_links) : 1);
      setTelegramChannels(r.source_config.telegram_channels || "");
      setToutiaoLinks(r.source_config.toutiao_links || "");
      const c=readHuntConditions(r.source_config); setConditions(c); setRegionInput(c.regions.join("，")); setCustomTime(!!c.start_at); setStartInput(utcToShanghaiInput(c.start_at)); setEndInput(utcToShanghaiInput(c.end_at));
    }).catch(reason => setError(reason instanceof Error ? reason.message : "读取编辑配置失败")).finally(() => setEditLoading(false));
  }, []);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("edit")) return;
    void localRequest<{ identity: LocalIdentity | null }>("/api/local/identity").then(data => { if (data.identity) setIdentityPrefill(data.identity); }).catch(() => { /* 身份设定不可用时保持默认表单 */ });
  }, []);
  useEffect(() => {
    void localRequest<{ account_remaining_requests?: number; account_remaining_cost_usd?: number }>("/api/billing/status")
      .then(data => setRemaining({ requests: data.account_remaining_requests, costUsd: data.account_remaining_cost_usd }))
      .catch(() => { /* 账本不可读时只显示“未知”，不编造剩余额度 */ });
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sourceError, setSourceError] = useState("");
  const loadSources = useCallback(() => { setSourceError(""); void localRequest<{ items: HuntSource[] }>("/api/local/sources").then(data => setCatalog(data.items)).catch(reason => setSourceError(reason instanceof Error ? reason.message : "平台状态读取失败")); }, []);
  useEffect(loadSources, [loadSources]);
  // 身份设定预填：仅在新建时应用一次，等平台目录就绪后按“可选平台”过滤默认平台。
  useEffect(() => {
    if (!identityPrefill || prefillApplied || editing || editLoading || !catalog.length) return;
    const available = catalog.filter(item => isHuntSourceSelectable(item)).map(item => item.id);
    const prefill = identityToRadarPrefill(identityPrefill, available);
    const preset = BUSINESS_PRESETS.find(item => item.id === prefill.presetId) ?? BUSINESS_PRESETS[0];
    setPresetId(preset.id);
    if (prefill.keywords.length) setKeywords(prefill.keywords.join("，"));
    if (prefill.businessTerms.length) setBusinessTerms(prefill.businessTerms.join("，"));
    if (prefill.excludes.length) setExcludeTerms(prefill.excludes.join("，"));
    if (prefill.hours) setHours(prefill.hours);
    if (prefill.sources.length) setSources(prefill.sources);
    if (prefill.regions.length) setRegionInput(prefill.regions.join("，"));
    setConditions(current => ({ ...current, ...(prefill.roles.length ? { roles: prefill.roles } : {}), match_mode: prefill.match_mode }));
    setPrefillApplied(true);
  }, [identityPrefill, prefillApplied, editing, editLoading, catalog]);
  const terms = splitTerms(keywords);
  const currentConditions = { ...conditions, regions: splitTerms(regionInput) };
  const groups = groupHuntSources(catalog);
  const tikhubAvailable = groups.available.filter(item => item.provider === "tikhub");
  const publicFree = groups.available.filter(item => item.provider !== "tikhub");
  const telegramParsed = parseTelegramChannels(telegramChannels);
  const toutiaoParsed = parseToutiaoLinks(toutiaoLinks);
  const telegramError = telegramChannelError(telegramChannels);
  const toutiaoError = toutiaoLinkError(toutiaoLinks);
  const queryPlan = platformQueries(terms, sources, currentConditions.regions, wechatScope);
  const estimate = estimateHunt({ catalog, sources, keywords: terms, regions: currentConditions.regions,
    remainingRequests: remaining.requests, remainingCostUsd: remaining.costUsd, singleRunLimitUsd: 0.1,
    wechatScope, wechatShareCount, telegramChannels, toutiaoLinks });
  const requests = estimate.requests;
  const blocked = sources.some(id => !catalog.find(item => item.id === id)?.available);
  const modeReady = (!sources.includes("telegram") || !telegramError) && (!sources.includes("toutiao") || !toutiaoError);
  const canSave = !editLoading && !estimate.overPlatformCap && !estimate.overCallCap && modeReady && catalog.length > 0 && sources.length > 0 && sources.every(id => catalog.some(item => item.id === id && isHuntSourceSelectable(item))) && terms.length > 0 && terms.length <= 3 && (!sources.includes("rss") || /^https?:\/\//.test(feedUrl.trim()));
  // 未填频道/链接时不允许保持选中：采集器也会拒绝，这里提前从选择中移除。
  useEffect(() => {
    if (sources.includes("telegram") && !parseTelegramChannels(telegramChannels).length) setSources(current => current.filter(id => id !== "telegram"));
  }, [telegramChannels, sources]);
  useEffect(() => {
    if (sources.includes("toutiao") && !parseToutiaoLinks(toutiaoLinks).length) setSources(current => current.filter(id => id !== "toutiao"));
  }, [toutiaoLinks, sources]);
  function choosePreset(id: string) { const next = BUSINESS_PRESETS.find(item => item.id === id)!; setPresetId(id); setKeywords(next.keywords); setBusinessTerms(next.terms.join("，")); }
  function toggleSource(id: string) { setSources(current => current.includes(id) ? current.filter(item => item !== id) : [...current, id]); }
  function pickWechatScope(scope: WechatScope) {
    const meta = wechatScopeMeta(scope);
    if (meta.state === "unavailable") return;
    setWechatScope(scope);
    if (!sources.includes("wechat_search")) setSources(current => [...current, "wechat_search"]);
  }
  async function submit(runNow: boolean) {
    setBusy(true); setError("");
    try {
      const c = { ...currentConditions };
      delete c.start_at; delete c.end_at;
      if (customTime) { if (!startInput || !endInput) throw new Error("请填写自定义起止时间（Asia/Shanghai）。"); c.start_at=shanghaiToUtc(startInput); c.end_at=shanghaiToUtc(endInput); }
      const payload = buildLeadRadar(preset, sources, keywords, customTime ? 720 : hours, feedUrl, splitTerms(businessTerms), c, splitTerms(excludeTerms), wechatScope, { wechatShareCount, telegramChannels: telegramParsed, toutiaoLinks: toutiaoParsed });
      if (radarName.trim()) payload.name=radarName.trim();
      if (editing) { payload.name=radarName.trim() || editing.name; payload.source_config={...editing.source_config,...payload.source_config}; payload.collection_policy={...payload.collection_policy,...editing.collection_policy,required_terms:splitTerms(businessTerms),excluded_terms:splitTerms(excludeTerms),time_basis:"published",include_unknown_dates:false}; }
      const radar = await localRequest<Radar>(editing ? `/api/radars/${encodeURIComponent(editing.id)}` : "/api/radars", { method: editing ? "PUT" : "POST", body: JSON.stringify(payload) });
      const saved = await localRequest<Radar>(`/api/radars/${encodeURIComponent(radar.id)}`);
      if (runNow) {
        try {
          const budgets = await fetchBudgets();
          if (!approveRun(budgets, message => window.confirm(message), saved.name)) { router.push(`/radars/${encodeURIComponent(saved.id)}`); return; }
          await runManualRadar<Run>(saved);
        }
        catch (reason) { router.push(`/radars/${encodeURIComponent(saved.id)}?dispatch_failed=${encodeURIComponent(reason instanceof Error ? reason.message : "提交失败")}`); return; }
      }
      router.push(`/radars/${encodeURIComponent(saved.id)}`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存抓单配置失败。"); }
    finally { setBusy(false); }
  }
  const statusTone = (item: HuntSource) => item.live_verified ? "text-emerald-700" : item.status.includes("不可用") || item.status.includes("不适用") ? "text-red-700" : item.status.includes("已覆盖") ? "text-indigo-700" : "text-amber-800";
  const capabilityRows = (item: HuntSource) => {
    const price = item.price_usd == null ? (item.provider === "public" ? "免费" : "未核验") : item.price_usd === 0 ? "免费" : `USD ${item.price_usd} / 请求（官方核价）`;
    const detail = item.implemented_capabilities?.detail ? "已接通" : "未接通";
    const comments = item.implemented_capabilities?.comments ? "已接通" : "未接通";
    const verified = (item.verified ?? item.live_verified) ? "已实测（有真实请求ID）" : item.validation_status === "covered_vertical" ? "垂类已实测" : "未实测";
    return [
      ["接入模式", item.mode_label ?? (item.id === "wechat_search" ? "公众号文章 / 视频号分享链" : "关键词搜索")],
      ["真实请求ID", item.request_id || item.share_link?.share_request_id || item.covered_request_id || "见运行记录"],
      ["原生时间筛选", item.time_policy ?? "未声明"],
      ["正文补抓", detail], ["评论补抓", comments], ["单价", price], ["实测状态", verified],
      ...(item.extra_call_price_usd ? [["附加调用", `USD ${item.extra_call_price_usd}/次 × ${item.extra_calls_per_item ?? 1} 次/条`]] : []),
      ...(item.limits ? [["限制", item.limits]] : []),
    ] as const;
  };
  const sourceCard = (item: HuntSource) => {
    const needsChannels = item.id === "telegram" && !telegramParsed.length;
    const needsLinks = item.id === "toutiao" && !toutiaoParsed.length;
    const selected = sources.includes(item.id);
    const selectable = isHuntSourceSelectable(item) && (selected || !(needsChannels || needsLinks));
    return <div key={item.id} data-source-card={item.id} className={`rounded-md border p-3 ${!isHuntSourceSelectable(item) ? "bg-slate-50" : ""} ${selected ? "border-indigo-300 bg-indigo-50/50" : "border-line"}`}>
      <label className={`flex items-start gap-3 ${selectable ? "cursor-pointer" : "cursor-not-allowed"}`}>
        <input type="checkbox" aria-label={`选择 ${item.name}`} disabled={!selectable} checked={selected} onChange={() => toggleSource(item.id)} className="mt-1"/>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-medium">{item.name} <span className={`text-xs ${statusTone(item)}`}>{item.status}</span></span>
          <span className="mt-1 block text-xs text-muted">
            {item.price_usd == null ? (item.provider === "public" ? "免费 · 无需密钥 · 可直接勾选" : "单价未核验") : item.price_usd === 0 ? "免费" : `USD ${item.price_usd}/请求`}
            {item.extra_call_price_usd ? ` · 分享链每条 +USD ${(item.extra_call_price_usd * (item.extra_calls_per_item ?? 1)).toFixed(2)}（${item.extra_calls_per_item ?? 1} 次调用）` : ""}
            {item.covered_by ? ` · 走 ${item.covered_by} 的 ${item.vertical} 垂类` : ""}
            {item.mode_label && item.provider === "tikhub" ? ` · ${item.mode_label}` : ""}
            {item.id === "douyin" ? " · 自动截短为 2–4 字短词（长短语实测 0 条）" : ""}
          </span>
        </span>
      </label>
      {item.id === "wechat_search" && <div className="mt-2 pl-7">
        <label className="block text-xs text-muted">搜索范围
          <select aria-label="微信搜一搜搜索范围" value={wechatScope} onChange={event => pickWechatScope(event.target.value as WechatScope)} className="mt-1 h-9 w-full rounded border border-line bg-white px-2 text-sm">
            {WECHAT_SCOPES.map(scope => <option key={scope.id} value={scope.id} disabled={scope.state === "unavailable"}>
              {scope.label}{scope.state === "verified" ? "（已实测）" : scope.state === "unavailable" ? "（不可用：无原文链接）" : "（未单独实测）"}
            </option>)}
          </select>
        </label>
        <p className="mt-1 text-xs leading-5 text-muted">{wechatScopeMeta(wechatScope).hint}</p>
        {wechatScope === "video" && <label className="mt-2 block text-xs text-muted">生成分享链条数（默认 1，最多 3）
          <select aria-label="视频号分享链条数" value={wechatShareCount} onChange={event => setWechatShareCount(Number(event.target.value))} className="mt-1 h-9 w-full rounded border border-line bg-white px-2 text-sm">
            {[1, 2, 3].map(count => <option key={count} value={count}>{count} 条 · 约 +USD {(0.02 * count).toFixed(2)} · 约 {30 * count} 秒</option>)}
          </select>
        </label>}
        {wechatScope === "video" && <p className="mt-1 text-xs leading-5 text-amber-900">每条 = 详情 1 次 + 分享链 1 次，各 USD 0.01；拿不到 weixin.qq.com/sph/ 短链就不生成假链接。</p>}
      </div>}
      {item.id === "telegram" && <div className="mt-2 pl-7">
        <label className="block text-xs text-muted">指定频道用户名（1–3 个，逗号分隔）
          <input aria-label="Telegram 频道用户名" value={telegramChannels} onChange={event => setTelegramChannels(event.target.value)} placeholder="@channel1, @channel2" className="mt-1 h-9 w-full rounded border border-line px-2 text-sm"/>
        </label>
        <p className={`mt-1 text-xs leading-5 ${telegramError ? "text-amber-900" : "text-muted"}`}>{telegramError || `将搜 ${telegramParsed.length} 个频道，每个 1 次请求（USD 0.001/频道）；这是频道内搜索，不是全站搜索。`}</p>
      </div>}
      {item.id === "toutiao" && <div className="mt-2 pl-7">
        <label className="block text-xs text-muted">头条文章链接（1–3 条，每行一条）
          <textarea aria-label="今日头条文章链接" rows={2} value={toutiaoLinks} onChange={event => setToutiaoLinks(event.target.value)} placeholder="https://www.toutiao.com/article/7450114952884503059/" className="mt-1 w-full rounded border border-line px-2 py-1 text-sm"/>
        </label>
        <p className={`mt-1 text-xs leading-5 ${toutiaoError ? "text-amber-900" : "text-muted"}`}>{toutiaoError || `将导入 ${toutiaoParsed.length} 条，每条 1 次请求（USD 0.001/条）；只支持按链接导入，不支持关键词搜索。`}</p>
      </div>}
      {item.id === "linkedin" && <p className="mt-2 pl-7 text-xs leading-5 text-muted">招聘信号：搜索职位后按公司/职位/地点/发布时间映射；在招视频岗位的公司通常有制作需求，但这不是买方直接需求。</p>}
      {item.covered_by && item.vertical === "article" && <div className="mt-2 pl-7"><Button variant="secondary" onClick={() => pickWechatScope("article")}>改用搜一搜「公众号文章」</Button></div>}
      {item.id === "wechat_channels" && <div className="mt-2 pl-7"><Button variant="secondary" onClick={() => pickWechatScope("video")}>选择视频号分享链模式</Button></div>}
      <details className="mt-2 pl-7 text-xs leading-5 text-muted" onClick={event => event.stopPropagation()}>
        <summary className="cursor-pointer">能力与限制</summary>
        <dl className="mt-1 grid grid-cols-[7rem_1fr] gap-x-2 gap-y-1">
          {capabilityRows(item).map(([label, value]) => <div key={label} className="contents"><dt className="text-slate-500">{label}</dt><dd className="break-words">{value}</dd></div>)}
        </dl>
        {item.verticals && <ul className="mt-2 space-y-1">{item.verticals.map(vertical => <li key={vertical.id}>{vertical.label}：{vertical.verified ? `已实测${vertical.total ? ` · 总量 ${vertical.total}` : ""} · 请求ID ${vertical.request_id}` : vertical.status === "fields_incomplete" ? `不可用 · 有 ${vertical.total} 条但无原文链接` : "未单独实测"}</li>)}</ul>}
        {!selectable && item.detail && <p className="mt-2 break-words">{item.detail.slice(0, 220)}</p>}
      </details>
    </div>;
  };
  const publicSection = <div className="mt-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-medium">其他公开 / 网页来源</h3><span className="text-xs text-muted">GitHub / Hacker News / RSS 免费、无需密钥、可直接选</span></div>
    {!publicFree.length && <p className="mt-2 text-sm text-muted">公开来源状态读取中…</p>}
    <div className="mt-2 grid gap-2 sm:grid-cols-2">{publicFree.map(sourceCard)}{groups.web.map(sourceCard)}</div>
  </div>;
  return <AppShell><PageHeader title={editing ? "编辑抓单条件" : "新建抓单"} description="业务 → 平台 → 关键词 → 条件 → 手动抓取 → 结果。只查首屏，不自动翻页。"/>
    <Panel className="max-w-3xl space-y-6 p-5"><label className="block text-sm"><span className="mb-2 block font-medium">雷达名称（可选）</span><input aria-label="雷达名称" value={radarName} onChange={e => setRadarName(e.target.value)} placeholder="例如：产品视频需求·手动验证" className="h-11 w-full rounded border border-line px-3"/></label>
      <label className="block text-sm"><span className="mb-2 block font-medium">1. 我的业务</span><select value={presetId} onChange={event => choosePreset(event.target.value)} className="h-11 w-full rounded-md border border-line bg-white px-3">{BUSINESS_PRESETS.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <fieldset><legend className="text-sm font-medium">2. 抓单平台</legend><p className="mt-2 text-xs leading-5 text-muted">已核对 TikHub 官方 OpenAPI：21 个平台/微信独立产品入口。可勾选不代表已授权；「不可用」默认折叠并写明真实原因。官方接口能力与本应用实际接入分开标明。</p>{!catalog.length && !sourceError && <p className="mt-2 text-sm text-muted">正在读取真实平台配置…</p>}{sourceError && <p role="alert" className="mt-2 text-sm text-red-800">{sourceError}<button className="ml-2 underline" onClick={loadSources}>重试</button></p>}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><h3 className="text-sm font-medium">可用平台（{tikhubAvailable.length}）</h3><div className="flex flex-wrap gap-2"><Button variant="secondary" onClick={() => setSources(selectAllAvailable(catalog).filter(id => (id !== "telegram" || telegramParsed.length > 0) && (id !== "toutiao" || toutiaoParsed.length > 0)))}>全选可用平台</Button><Button variant="secondary" onClick={() => setSources([])}>清空</Button></div></div>
        <p className="mt-1 text-xs text-muted">全选会同时选中 GitHub / Hacker News / RSS（免费）；Telegram / 今日头条需先填频道/链接才会被全选。每轮最多 10 次调用（6 次首屏查询 + 分享链/频道/链接附加调用）。</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">{tikhubAvailable.map(sourceCard)}</div>
        {publicSection}
        <div className="mt-4"><h3 className="text-sm font-medium">微信垂类（{groups.covered.length}）</h3><p className="mt-1 text-xs text-muted">公众号文章 = 搜一搜 article 垂类（已实测）；视频号视频 = 搜一搜 video 垂类 + 逐条分享链（已实测：每条额外 2 次调用，单条约 30 秒）。</p><div className="mt-2 grid gap-2 sm:grid-cols-2">{groups.covered.map(sourceCard)}</div></div>
        <div className="mt-4"><button type="button" aria-expanded={showUnavailable} onClick={() => setShowUnavailable(value => !value)} className="text-sm text-muted underline">不可用平台（{groups.unavailable.length}）{showUnavailable ? "收起" : "展开原因与能力"}</button>{showUnavailable && <div className="mt-2 grid gap-2 sm:grid-cols-2">{groups.unavailable.map(sourceCard)}</div>}</div>
      </fieldset>
      {sources.includes("rss") && <label className="block text-sm"><span className="mb-1 block">RSS 公网订阅地址</span><input type="url" value={feedUrl} onChange={event => setFeedUrl(event.target.value)} placeholder="https://example.com/feed.xml" className="h-11 w-full rounded-md border border-line px-3"/></label>}
      <div className="block text-sm"><span className="mb-2 block font-medium">3. 买方搜索关键词（可改，1–3 个，逗号分隔）</span><textarea aria-label="买方搜索关键词" value={keywords} onChange={event => setKeywords(event.target.value)} rows={2} className="w-full rounded-md border border-line px-3 py-2"/><span className="mt-1 block text-xs text-muted">使用“求、找人、需要、外包需求”等买方表达；搜索命中不等于真实客户。</span>
        <div className="mt-2 flex flex-wrap items-center gap-2"><span className="text-xs text-muted">按业务生成的模板：</span>{preset.keywordTemplates.map((template, index) => <button type="button" key={template} onClick={() => setKeywords(template)} className="rounded border border-line px-2 py-1 text-xs hover:bg-slate-50">{index + 1}. {template}</button>)}</div>
        <p className="mt-1 text-xs leading-5 text-muted">抖音会自动截短为 2–4 字短词（父代理已实测：长短语 0 条、短词 8–1000 条），其他平台保留长短语；下方“查询预览”按平台显示实际发出的词。</p>
      </div>
      <label className="block text-sm"><span className="mb-1 block text-muted">业务匹配词（原文至少命中一个，可改）</span><input value={businessTerms} onChange={event => setBusinessTerms(event.target.value)} className="h-11 w-full rounded-md border border-line px-3"/></label>
      <div className="block text-sm"><span className="mb-1 block text-muted">排除词（命中即过滤，可改；默认来自你的身份设定）</span><input aria-label="排除词" value={excludeTerms} onChange={event => setExcludeTerms(event.target.value)} placeholder="例如：教程，招聘，代做，承接，招生" className="h-11 w-full rounded-md border border-line px-3"/>
        <div className="mt-2 flex flex-wrap items-center gap-2">{splitTerms(excludeTerms).map(term => <span key={term} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs">{term}<button type="button" aria-label={`移除排除词 ${term}`} onClick={() => setExcludeTerms(splitTerms(excludeTerms).filter(item => item !== term).join("，"))} className="text-muted">×</button></span>)}{!splitTerms(excludeTerms).length && <span className="text-xs text-muted">当前没有排除词</span>}<Link href="/settings" className="text-xs text-ai underline">去身份设定修改</Link></div>
        <span className="mt-1 block text-xs text-muted">排除词写入采集策略，由现有采后过滤真实剔除；老雷达在你再次编辑前不受影响。</span>
      </div>
      <label className="block text-sm"><span className="mb-2 block font-medium">4. 原文发布时间（统一本地过滤窗口）</span><select aria-label="发布时间窗口" value={customTime ? "custom" : hours} onChange={event => { setCustomTime(event.target.value === "custom"); if (event.target.value !== "custom") setHours(Number(event.target.value)); }} className="h-11 rounded-md border border-line bg-white px-3"><option value={24}>最近 24 小时</option><option value={72}>最近 3 天</option><option value={168}>最近 7 天（默认）</option><option value={720}>最近 30 天</option><option value="custom">自定义起止时间</option></select><span className="mt-2 block text-xs leading-5 text-muted">按原始发布时间过滤，时间未知的内容不进入本次结果。这里不是所有平台都支持的原生搜索档位；只过滤取回首屏，不代表全量搜索。{catalog.filter(item => sources.includes(item.id)).map(item => `${item.name}：${item.time_policy ?? "仅本地过滤。"}`).join(" ")}</span></label>
      {customTime && <div className="grid gap-3 sm:grid-cols-2"><label className="text-sm">开始时间（Asia/Shanghai）<input aria-label="开始时间" type="datetime-local" value={startInput} onChange={e => setStartInput(e.target.value)} className="mt-1 h-11 w-full rounded border border-line px-3"/></label><label className="text-sm">结束时间（Asia/Shanghai）<input aria-label="结束时间" type="datetime-local" value={endInput} onChange={e => setEndInput(e.target.value)} className="mt-1 h-11 w-full rounded border border-line px-3"/></label><p className="text-xs text-muted sm:col-span-2">跨度最多30天；保存为UTC。自定义范围不会让平台首屏自动补齐历史。</p></div>}
      <fieldset><legend className="text-sm font-medium">5. 需求地区</legend><label className="mt-2 block text-sm">项目 / 服务所在地（不是作者 IP）<input aria-label="需求地区" value={regionInput} onChange={e => setRegionInput(e.target.value)} placeholder="全国（留空）；省市多选，逗号分隔，最多10个" className="mt-1 h-11 w-full rounded border border-line px-3"/></label><div className="mt-2 flex flex-wrap gap-2"><Button variant="secondary" onClick={() => setRegionInput("")}>全国</Button>{["广东","广州","深圳","佛山"].map(r => <Button key={r} variant="secondary" onClick={() => { const values=splitTerms(regionInput); setRegionInput((values.includes(r) ? values.filter(v => v!==r) : [...values,r]).join("，")); }}>{splitTerms(regionInput).includes(r) ? "✓ " : ""}{r}</Button>)}</div><div className="mt-2 flex flex-wrap gap-2">{splitTerms(regionInput).map(r => <span key={r} className="rounded bg-indigo-50 px-2 py-1 text-xs">{r}</span>)}</div><p className="mt-2 text-xs text-muted">所选地区为“或”；规则仅核实原文地点语境，不从昵称、IP、简介或查询词推断。省市不自动展开为全辖区。</p></fieldset>
      <fieldset><legend className="text-sm font-medium">6. 目标人群（业务角色，可多选）</legend><div className="mt-2 flex flex-wrap gap-4">{HUNT_ROLES.map(role => <label key={role} className="text-sm"><input type="checkbox" checked={conditions.roles.includes(role)} onChange={() => setConditions(c => ({...c,roles:c.roles.includes(role) ? c.roles.filter(v => v!==role) : [...c.roles,role]}))}/> {role}</label>)}</div><p className="mt-2 text-xs text-muted">不选即不限；多选命中任一即可。只认正文自述职业，不推断年龄、收入；角色不明为待确认。</p></fieldset>
      <fieldset><legend className="text-sm font-medium">7. 需求意图（可多选）</legend><div className="mt-2 flex flex-wrap gap-4">{HUNT_INTENTS.map(intent => <label key={intent} className="text-sm"><input type="checkbox" checked={conditions.intents.includes(intent)} onChange={() => setConditions(c => ({...c,intents:c.intents.includes(intent) ? c.intents.filter(v => v!==intent) : [...c.intents,intent]}))}/> {intent}</label>)}</div><p className="mt-2 text-xs text-muted">所选意图为“或”。仍需原文买方表达；卖方推广不当作采购需求，预算未知不扣为不匹配。</p></fieldset>
      <label className="block text-sm"><span className="mb-2 block font-medium">8. 本地 / 远程匹配模式</span><select aria-label="匹配模式" value={conditions.match_mode} onChange={e => setConditions(c => ({...c,match_mode:e.target.value as HuntConditions["match_mode"]}))} className="h-11 w-full rounded border border-line bg-white px-3"><option value="remote">远程优先 · 地区未知待确认（默认）</option><option value="local">严格本地 · 有地区证据优先，未知降序待确认</option><option value="keep_unknown">保留地区未知待确认</option></select></label>
      <div className="rounded-md border border-line bg-slate-50 p-3 text-sm leading-6"><p>本次条件：{customTime ? `${startInput || "待填"} 至 ${endInput || "待填"}（上海时间）` : `${hours}小时内`} · {regionInput || "全国"} · {conditions.roles.join(" / ") || "角色不限"} · {conditions.intents.join(" / ") || "意图不限"} · {{local:"严格本地",remote:"远程优先",keep_unknown:"保留未知"}[conditions.match_mode]}</p>
        <div className="mt-2 rounded border border-line bg-white p-2"><p className="font-medium">查询预览（按平台实际发出）</p>{estimate.overPlatformCap ? <p className="mt-1 text-xs text-red-800">已选 {sources.length} 个平台，超过每轮 6 次首屏查询上限；受限模式按 1 个查询计。请先减少平台再看实际查询词。</p> : queryPlan.length ? <ul className="mt-1 space-y-1 text-xs">{queryPlan.map(group => <li key={group.source}><span className="font-medium">{sourceNames[group.source] ?? catalog.find(item => item.id === group.source)?.name ?? group.source}</span>：{group.queries.join("；") || "（无可用短词，需改关键词）"}</li>)}</ul> : <p className="mt-1 text-xs text-muted">先填关键词并选择平台。</p>}</div>
        <p className="mt-2">{estimate.overPlatformCap ? <>请求估算：平台/首屏查询超限，请减少平台。</> : <>请求估算：首屏查询 <span className="font-semibold">{requests - estimate.extraRequests}</span> 次 + 附加调用 <span className="font-semibold">{estimate.extraRequests}</span> 次 = <span className="font-semibold">{requests} 次调用</span> ≈ <span className="font-semibold">USD {estimate.costUsd.toFixed(3)}</span>{estimate.extraRequests > 0 ? "（分享链/频道/链接已计入）" : ""}</>}</p>
        <p className="text-xs">本日剩余：{remaining.requests ?? "未知"} 次请求 / USD {remaining.costUsd?.toFixed(3) ?? "未知"}（来自账本；硬上限 20 次 / USD 1）。单轮上限 USD 0.10。</p>
        {estimate.note && <p className="text-xs text-amber-900">{estimate.note}</p>}
        {estimate.overCallCap && <p role="alert" className="text-xs font-medium text-red-800">本轮需要 {requests} 次调用，超过每轮 {MAX_RUN_REQUESTS} 次硬上限；请减少平台或分享链条数。</p>}
        {estimate.exceedsDaily && <p role="alert" className="text-xs font-medium text-red-800">超出可用额度：保存后无法启动，请减少平台、关键词或分享链条数。</p>}
        <p>手动运行 · 本轮计划 {requests} 次调用（含附加）· 不翻页 · 不自动调用 AI</p>
        <p className="text-amber-900">点击运行即授权本雷达 TikHub 手动采集：每轮最多 USD 0.10、每日最多 USD 1 / 20 请求，不授权自动调度；实际费用以平台账单为准。</p>
        <p className="text-xs">地区、角色、意图仅为可解释规则；摘要命中仍待正文确认，不保证精准识别。时间UTC保存、Asia/Shanghai展示；评论时间不代替原帖时间。每个选中平台必须 ≥1 条入库，否则本轮标记「未达标」。</p>{blocked && <p className="text-amber-900">所选平台包含未配置或未授权来源：可以保存配置，但不能从这里启动抓取。未绕过现有付费开关、价格核验和授权。</p>}</div>
      {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
      <div className="flex flex-wrap justify-end gap-2"><Link href="/radars"><Button variant="secondary">返回抓单列表</Button></Link><Button variant="secondary" disabled={!canSave || busy} onClick={() => void submit(false)}>仅保存配置</Button><Button disabled={!canSave || busy || blocked} onClick={() => void submit(true)}>{busy ? "保存中…" : "保存并手动运行"}</Button></div>
    </Panel>
  </AppShell>;
}

export function LocalSettings() {
  const [mode, setMode] = useState<"off" | "on_demand">("off");
  const [reason, setReason] = useState("");
  const [paidManual, setPaidManual] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { void localRequest<{ ai_mode: "off" | "on_demand"; ai_reason?: string; paid_calls_available?: boolean }>("/api/local/settings").then(value => { setPaidManual(!!value.paid_calls_available); setMode(value.ai_mode); setReason(value.ai_reason ?? ""); }).catch(reason => setError(reason instanceof Error ? reason.message : "设置暂不可用。" )).finally(() => setLoading(false)); }, []);
  async function save(value: "off" | "on_demand") {
    setBusy(true); setError("");
    try { const result = await localRequest<{ ai_mode: "off" | "on_demand"; ai_reason?: string }>("/api/local/settings", { method: "PUT", body: JSON.stringify({ ai_mode: value }) }); setMode(result.ai_mode); setReason(result.ai_reason ?? ""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "设置保存失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <AppShell><PageHeader title="设置" description="Local Edition 默认关闭付费调用、自动 AI 和保留期清理。"/>
    {error && <Panel role="alert" className="mb-4 border-red-200 p-3"><p className="text-sm text-red-800">{error}</p></Panel>}
    <div className="max-w-3xl space-y-7"><section><h2 className="mb-3 font-semibold">分析方式</h2><Panel className="p-5"><p className="text-sm text-muted">自动采集只使用规则筛选与可解释排序。按需模式仅在你点击单条信息的分析按钮时尝试模型；未配置或未授权时回退到现有规则结果。</p><div className="mt-4 flex flex-wrap gap-2"><Button variant={mode === "off" ? "primary" : "secondary"} disabled={loading || busy} onClick={() => void save("off")}>关闭 AI</Button><Button variant={mode === "on_demand" ? "primary" : "secondary"} disabled={loading || busy} onClick={() => void save("on_demand")}>按需分析</Button></div>{reason && <p className="mt-3 text-xs text-amber-900">{reason}</p>}{loading && <p className="mt-3 text-xs text-muted">读取设置…</p>}</Panel></section>
      <section><h2 className="mb-3 font-semibold">个人身份设定</h2><LocalIdentitySection/></section>
      <section><h2 className="mb-3 font-semibold">API 与预算</h2><LocalProviderSection/></section>
      <section><h2 className="mb-3 font-semibold">Agent 接入</h2><LocalAgentSection/></section>
      <section><h2 className="mb-3 font-semibold">费用与数据</h2><Panel className="divide-y divide-line"><p className="py-3 text-sm first:pt-0"><span className="font-medium">TikHub 手动采集</span><span className="ml-3 text-muted">{paidManual ? "已启用 · 每轮≤USD 0.10 / 每日≤USD 1" : "关闭"}</span></p><p className="py-3 text-sm"><span className="font-medium">自动分类模型</span><span className="ml-3 text-muted">关闭</span></p><p className="py-3 text-sm"><span className="font-medium">本地分类器</span><span className="ml-3 text-muted">关闭</span></p><p className="py-3 text-sm last:pb-0"><span className="font-medium">自动删除历史记录</span><span className="ml-3 text-muted">关闭</span></p><p className="mt-3 text-xs leading-5 text-muted">所有业务数据写入独立 PostgreSQL 数据库；备份与恢复由本机脚本管理。</p></Panel></section>
      <section><h2 className="mb-3 font-semibold">运行模式</h2><Panel className="p-5"><p className="flex items-center gap-2 text-sm"><CircleCheck size={16} className="text-emerald-700"/>本机单用户 · PostgreSQL 持久化 · Redis 后台队列</p><p className="mt-2 text-xs text-muted">服务绑定 loopback；Next.js 通过同源代理访问 FastAPI。需要远程访问时请使用受保护的私有网络与额外访问控制。</p></Panel></section>
    </div>
  </AppShell>;
}
