"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Bookmark, ExternalLink, Loader2, RefreshCw, Search, Sparkles } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, DetailDrawer, EmptyState, PageHeader, Panel } from "@/components/ui";
import { formatLocalDate, localRequest } from "@/lib/local-edition";

type FeedItem = { evidence_id: string; source: string; url: string; raw_text: string; query: string; category: string; published_at: string | null; captured_at: string; is_saved: boolean; is_read: boolean; classification_reason: string; classification_confidence: number; verification_status: string; metadata: Record<string, string>; radars: { radar_id: string; name: string; mode: string; relevance_score: number; relevance_reasons: string[] }[]; intelligence_ranking?: { score: number; reasons: string[]; label: string } | null };
type FeedPage = { items: FeedItem[]; next_cursor: string | null; has_more: boolean };
type Analysis = { source: "model" | "rules"; category: string; confidence: number; reason: string; fallback_reason: string | null; intent_quote: string | null; payment_quote: string | null; deadline_quote: string | null; saved: false };
type Radar = { id: string; name: string };
const categories = [["", "全部类别"], ["buyer", "买方需求"], ["seller", "服务推广"], ["job", "招聘与求职"], ["content", "教程与内容"], ["market", "行业与市场"]] as const;

function headline(item: FeedItem) { return item.raw_text.split("\n").find(Boolean)?.slice(0, 180) || "（无标题）"; }
function firstRadarScore(item: FeedItem) { return item.intelligence_ranking?.score ?? item.radars?.[0]?.relevance_score; }

export default function LocalInbox() {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [radars, setRadars] = useState<Radar[]>([]);
  const [category, setCategory] = useState("");
  const [state, setState] = useState("all");
  const [order, setOrder] = useState("recent");
  const [radarId, setRadarId] = useState("");
  const [source, setSource] = useState("");
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [selectedExtra, setSelectedExtra] = useState<FeedItem | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [wide, setWide] = useState(false);
  const [aiMode, setAiMode] = useState<"off" | "on_demand">("off");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSelectedId(params.get("selected") ?? "");
    setRadarId(params.get("radar_id") ?? "");
    if (params.get("saved") === "true") setState("saved");
  }, []);
  useEffect(() => { const media = matchMedia("(min-width: 1280px)"); const sync = () => setWide(media.matches); sync(); media.addEventListener("change", sync); return () => media.removeEventListener("change", sync); }, []);
  useEffect(() => { void localRequest<Radar[]>("/api/radars").then(setRadars).catch(() => setRadars([])); }, []);
  useEffect(() => { void localRequest<{ ai_mode: "off" | "on_demand" }>("/api/local/settings").then(value => setAiMode(value.ai_mode)).catch(() => setAiMode("off")); }, []);
  useEffect(() => { setAnalysis(null); }, [selectedId]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ limit: "40", order });
    if (category) params.set("category", category);
    if (state === "saved") params.set("saved", "true");
    if (state === "unread") params.set("unread", "true");
    if (radarId) params.set("radar_id", radarId);
    if (source) params.set("source", source);
    if (appliedSearch.trim()) params.set("q", appliedSearch.trim());
    return params.toString();
  }, [category, state, order, radarId, source, appliedSearch]);

  const load = useCallback(async (append = false, next = cursor) => {
    if (append) setLoadingMore(true); else { setLoading(true); setItems([]); setCursor(null); }
    setError("");
    try {
      const params = new URLSearchParams(queryString);
      if (append && next) params.set("cursor", next);
      const page = await localRequest<FeedPage>(`/api/intelligence/evidence/inbox?${params.toString()}`);
      setItems(previous => append ? [...previous, ...page.items] : page.items);
      setCursor(page.next_cursor); setHasMore(page.has_more);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "收件箱暂不可用。"); }
    finally { setLoading(false); setLoadingMore(false); }
  }, [cursor, queryString]);
  useEffect(() => { void load(false, null); }, [load]);

  const selected = items.find(item => item.evidence_id === selectedId) ?? (selectedExtra?.evidence_id === selectedId ? selectedExtra : null);
  useEffect(() => {
    if (!selectedId || items.some(item => item.evidence_id === selectedId)) return;
    void localRequest<FeedItem>(`/api/intelligence/evidence/${encodeURIComponent(selectedId)}`).then(setSelectedExtra).catch(() => setSelectedExtra(null));
  }, [selectedId, items]);
  useEffect(() => {
    if (!selected || selected.is_read) return;
    void localRequest<FeedItem>(`/api/intelligence/evidence/${encodeURIComponent(selected.evidence_id)}/state`, { method: "PATCH", body: JSON.stringify({ read: true }) })
      .then(updated => { setItems(previous => previous.map(item => item.evidence_id === updated.evidence_id ? updated : item)); setSelectedExtra(updated); })
      .catch(() => undefined);
  }, [selected]);

  function select(item: FeedItem) {
    setSelectedId(item.evidence_id);
    const params = new URLSearchParams(window.location.search);
    params.set("selected", item.evidence_id);
    history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
  }
  async function toggleSaved(item: FeedItem) {
    setError("");
    try {
      const updated = await localRequest<FeedItem>(`/api/intelligence/evidence/${encodeURIComponent(item.evidence_id)}/state`, { method: "PATCH", body: JSON.stringify({ saved: !item.is_saved }) });
      setItems(previous => previous.map(current => current.evidence_id === updated.evidence_id ? updated : current));
      setSelectedExtra(updated);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "收藏状态未保存，请重试。"); }
  }
  async function analyze(item: FeedItem) {
    setAnalyzing(true); setAnalysis(null); setError("");
    try { setAnalysis(await localRequest<Analysis>(`/api/local/evidence/${encodeURIComponent(item.evidence_id)}/analyze`, { method: "POST", body: "{}" })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "单条分析失败。"); }
    finally { setAnalyzing(false); }
  }

  const detail = selected ? <div className="space-y-4 p-4">
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted"><span className="rounded bg-slate-100 px-2 py-1">{selected.source}</span><span>{selected.category}</span><span>{formatLocalDate(selected.published_at)}</span><span>采集于 {formatLocalDate(selected.captured_at)}</span></div>
    <div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm">人工状态：{selected.verification_status === "verified" ? "已核实" : selected.verification_status === "invalidated" ? "已排除" : "待复核"}</p><Button variant="secondary" onClick={() => void toggleSaved(selected)}><Bookmark size={15} fill={selected.is_saved ? "currentColor" : "none"}/>{selected.is_saved ? "已收藏" : "收藏"}</Button></div>
    {aiMode === "on_demand" && <div><Button variant="secondary" disabled={analyzing} onClick={() => void analyze(selected)}><Sparkles size={15}/>{analyzing ? "分析中…" : "单条按需分析"}</Button>{analysis && <div className="mt-3 rounded-md bg-slate-50 p-3"><p className="text-sm font-medium">{analysis.category} · {analysis.source === "model" ? "模型结果" : "规则回退"} · 置信度 {Math.round(analysis.confidence * 100)}%</p><p className="mt-1 text-sm text-muted">{analysis.reason || "无分类说明"}</p>{analysis.fallback_reason && <p className="mt-2 text-xs text-amber-900">{analysis.fallback_reason}</p>}{analysis.intent_quote && <p className="mt-2 text-xs">需求原文：“{analysis.intent_quote}”</p>}{analysis.payment_quote && <p className="mt-1 text-xs">付费依据：“{analysis.payment_quote}”</p>}{analysis.deadline_quote && <p className="mt-1 text-xs">时间依据：“{analysis.deadline_quote}”</p>}<p className="mt-2 text-xs text-muted">结果仅在本次详情中展示，未保存、未改变人工核实状态。</p></div>}</div>}
    {selected.radars?.length > 0 && <div><h3 className="text-xs font-medium text-muted">发现主题</h3><p className="mt-1 text-sm">{selected.radars.map(radar => radar.name).join("、")}</p></div>}
    {firstRadarScore(selected) != null && <div><h3 className="text-xs font-medium text-muted">情报相关度</h3><p className="mt-1 text-2xl font-semibold tabular-nums">{firstRadarScore(selected)}<span className="ml-1 text-sm font-normal text-muted">/100 · 排序启发式</span></p><p className="mt-1 text-xs text-muted">不代表买方意向或成交概率。</p></div>}
    {selected.intelligence_ranking?.reasons?.length ? <ul className="list-disc space-y-1 pl-5 text-xs leading-5 text-muted">{selected.intelligence_ranking.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul> : null}
    {selected.classification_reason && <div><h3 className="text-xs font-medium text-muted">规则分类依据</h3><p className="mt-1 text-sm">{selected.classification_reason}</p></div>}
    <div className="border-t border-line pt-4"><h3 className="mb-2 text-xs font-medium text-muted">原始内容</h3><pre className="whitespace-pre-wrap break-words font-sans text-sm leading-7">{selected.raw_text}</pre></div>
    <a href={selected.url} target="_blank" rel="noreferrer" className="inline-flex min-h-11 items-center gap-2 text-sm text-ai underline">打开原文 <ExternalLink size={15}/></a>
  </div> : <p className="p-8 text-center text-sm text-muted">选择一条信息查看详情。</p>;

  return <AppShell>
    <PageHeader title="情报收件箱" description="按主题、来源和状态筛选公开信息；打开详情只更新已读状态，不更改人工核实结论。" action={<Link href="/radars/new"><Button>新建关注主题</Button></Link>}/>
    <form className="mb-4 flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); setAppliedSearch(search); }}>
      <label className="relative min-w-56 flex-1"><Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted"/><input aria-label="搜索情报" value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索原文、关键词或链接" className="h-11 w-full rounded-md border border-line bg-white pl-8 pr-3 text-sm"/></label><Button variant="secondary" type="submit">搜索</Button>
      <select aria-label="情报类别" className="h-11 rounded-md border border-line bg-white px-2 text-sm" value={category} onChange={event => setCategory(event.target.value)}>{categories.map(([value,label]) => <option value={value} key={value}>{label}</option>)}</select>
      <select aria-label="收件箱状态" className="h-11 rounded-md border border-line bg-white px-2 text-sm" value={state} onChange={event => setState(event.target.value)}><option value="all">全部状态</option><option value="unread">未读</option><option value="saved">收藏</option></select>
      <select aria-label="关注主题" className="h-11 max-w-48 rounded-md border border-line bg-white px-2 text-sm" value={radarId} onChange={event => setRadarId(event.target.value)}><option value="">所有主题</option>{radars.map(radar => <option key={radar.id} value={radar.id}>{radar.name}</option>)}</select>
      <select aria-label="内容来源" className="h-11 rounded-md border border-line bg-white px-2 text-sm" value={source} onChange={event => setSource(event.target.value)}><option value="">全部来源</option>{[...new Set(items.map(item => item.source))].sort().map(value => <option key={value} value={value}>{value}</option>)}</select>
      <select aria-label="排序方式" className="h-11 rounded-md border border-line bg-white px-2 text-sm" value={order} onChange={event => setOrder(event.target.value)}><option value="recent">最近采集</option><option value="relevance">主题相关度</option><option value="saved">收藏优先</option></select>
    </form>
    {error && <Panel className="mb-3 border-red-200 p-3" role="alert"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm text-red-800">{error}</span><Button variant="secondary" disabled={loading} onClick={() => void load(false, null)}><RefreshCw size={15}/>重试</Button></div></Panel>}
    {loading && !items.length ? <Panel className="flex items-center gap-2 p-10 text-sm text-muted"><Loader2 className="animate-spin" size={18}/>正在加载情报…</Panel> : !loading && !error && !items.length ? <EmptyState title="暂无匹配情报"><p className="text-sm text-muted">可以修改筛选条件，或到我的雷达创建主题并手动运行。</p><Link href="/radars/new"><Button className="mt-4">创建主题雷达</Button></Link></EmptyState> : <div className="grid items-start gap-0 rounded-lg border border-line bg-white xl:grid-cols-[minmax(0,1fr)_400px]">
      <div className="min-w-0"><div className="flex min-h-10 items-center justify-between border-b border-line bg-slate-50 px-4 text-xs text-muted"><span>{items.length} 条信息</span><span>无数据不代表零机会</span></div><div className="divide-y divide-line">{items.map(item => <div key={item.evidence_id} className={`border-l-2 px-4 py-3 ${selectedId === item.evidence_id ? "border-ai bg-indigo-50/50" : "border-transparent"}`}><button type="button" onClick={() => select(item)} className="block w-full text-left"><span className="line-clamp-2 text-sm font-medium leading-6">{headline(item)}</span><span className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted"><span>{item.source}</span><span>{formatLocalDate(item.published_at)}</span>{firstRadarScore(item) != null && <span>相关度 {firstRadarScore(item)}</span>}<span>{item.is_read ? "已读" : "未读"}</span></span></button></div>)}</div>{hasMore && <div className="border-t border-line p-3 text-center"><Button variant="secondary" disabled={loadingMore} onClick={() => void load(true)}>{loadingMore && <Loader2 className="animate-spin" size={15}/>}加载更多</Button></div>}</div>
      <aside className="sticky top-20 hidden max-h-[calc(100vh-100px)] overflow-y-auto border-l border-line xl:block">{detail}</aside>
    </div>}
    <DetailDrawer open={!wide && !!selected} title="情报详情" onClose={() => { setSelectedId(""); const params = new URLSearchParams(window.location.search); params.delete("selected"); history.replaceState(null, "", params.size ? `${window.location.pathname}?${params}` : window.location.pathname); }}>{detail}</DetailDrawer>
  </AppShell>;
}
