"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Bookmark, CircleAlert, CircleCheck, Loader2, Radar, RefreshCw } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, EmptyState, PageHeader, Panel } from "@/components/ui";
import { apiRequest } from "@/lib/api-client";
import { getAccessToken } from "@/lib/auth";

type FeedItem = { evidence_id: string; source: string; url: string; raw_text: string; captured_at: string; published_at: string | null; is_saved: boolean; intelligence_ranking?: { score?: number; reasons?: string[]; label?: string } | null };
type RadarItem = { id: string; name: string; mode: "general" | "acquisition"; status: string; last_run_at: string | null };
type RunItem = { id: string; radar_id: string; status: string; error_message?: string | null; error_code?: string | null; started_at?: string | null; finished_at?: string | null };
type Overview = { latest: FeedItem[]; relevant: FeedItem[]; saved: FeedItem[]; radars: RadarItem[]; runs: RunItem[]; ai_mode: string };

async function localGet<T>(path: string): Promise<T> {
  const token = await getAccessToken();
  if (!token) throw new Error("本地会话已失效，请重新配对。");
  return apiRequest<T>(path, { cache: "no-store" }, token);
}

function headline(item: FeedItem) { return item.raw_text.split("\n").find(Boolean)?.slice(0, 180) || "（无标题）"; }
function dateLabel(value?: string | null) { if (!value) return "时间未知"; const date = new Date(value); return Number.isNaN(date.getTime()) ? "时间未知" : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date); }

function EvidenceRows({ items, empty }: { items: FeedItem[]; empty: string }) {
  if (!items.length) return <p className="py-8 text-sm text-muted">{empty}</p>;
  return <div className="divide-y divide-line">{items.map(item => <Link key={item.evidence_id} href={`/evidence?selected=${encodeURIComponent(item.evidence_id)}`} className="block py-3 first:pt-0 last:pb-0 hover:text-ai">
    <p className="line-clamp-2 text-sm font-medium leading-6">{headline(item)}</p>
    <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted"><span>{item.source}</span><span>{dateLabel(item.published_at)}</span>{item.intelligence_ranking?.score != null && <span>相关度 {item.intelligence_ranking.score}</span>}{item.is_saved && <span className="inline-flex items-center gap-1"><Bookmark size={12}/>已收藏</span>}</p>
  </Link>)}</div>;
}

export default function LocalDashboard() {
  const [data, setData] = useState<Overview | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setBusy(true); setError("");
    try { setData(await localGet<Overview>("/api/local/overview")); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "首页数据暂不可用。"); }
    finally { setBusy(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const radarNames = new Map((data?.radars ?? []).map(item => [item.id, item.name]));
  return <AppShell>
    <PageHeader title="情报工作台" description="关注主题、运行状态和最近发现都来自本地数据库。" action={<Link href="/radars/new"><Button><Radar size={16}/> 新建雷达</Button></Link>}/>
    {error && <Panel className="mb-5 border-red-200 p-4" role="alert"><p className="text-sm text-red-800">{error}</p><Button className="mt-3" variant="secondary" disabled={busy} onClick={() => void load()}><RefreshCw size={15}/> 重试</Button></Panel>}
    {busy && !data ? <Panel className="flex items-center gap-2 p-8 text-sm text-muted"><Loader2 size={17} className="animate-spin"/>正在读取本地情报…</Panel> : data && <div className="grid gap-7 xl:grid-cols-[minmax(0,1.5fr)_minmax(280px,.8fr)]">
      <div className="space-y-8">
        <section><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">最新发现</h2><Link href="/evidence" className="inline-flex min-h-11 items-center gap-1 text-sm text-ai">打开收件箱 <ArrowRight size={15}/></Link></div><Panel className="p-4"><EvidenceRows items={data.latest} empty="暂无情报。创建一个主题雷达并手动运行后，结果会显示在这里。"/></Panel></section>
        <section><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">主题相关度靠前</h2><span className="text-xs text-muted">启发式排序，不代表客户意向或成交概率</span></div><Panel className="p-4"><EvidenceRows items={data.relevant} empty="暂无可排序的情报。"/></Panel></section>
      </div>
      <aside className="space-y-7">
        <section><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">我的雷达</h2><Link href="/radars" className="text-sm text-ai">全部</Link></div><Panel className="p-4">{data.radars.length ? <div className="divide-y divide-line">{data.radars.slice(0, 6).map(radar => <Link key={radar.id} href={`/radars?selected=${encodeURIComponent(radar.id)}`} className="block py-3 first:pt-0 last:pb-0"><span className="font-medium">{radar.name}</span><span className="mt-1 block text-xs text-muted">{radar.mode === "general" ? "通用情报" : "获客雷达"} · {radar.status} · 最近运行 {dateLabel(radar.last_run_at)}</span></Link>)}</div> : <EmptyState title="还没有雷达"><Link href="/radars/new" className="text-ai underline">创建关注主题</Link></EmptyState>}</Panel></section>
        <section><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold">收藏</h2><Link href="/evidence?saved=true" className="inline-flex min-h-11 items-center gap-1 text-sm text-ai"><Bookmark size={14}/>查看</Link></div><Panel className="p-4"><EvidenceRows items={data.saved} empty="暂无收藏内容。"/></Panel></section>
        <section><h2 className="mb-3 font-semibold">最近运行</h2><Panel className="p-4">{data.runs.length ? <div className="divide-y divide-line">{data.runs.slice(0, 6).map(run => <div key={run.id} className="py-3 first:pt-0 last:pb-0"><p className="flex items-center gap-2 text-sm"><span>{radarNames.get(run.radar_id) ?? "已删除的雷达"}</span>{run.status === "failed" ? <CircleAlert size={15} className="text-red-700"/> : run.status === "completed" ? <CircleCheck size={15} className="text-emerald-700"/> : <Loader2 size={14} className="animate-spin text-muted"/>}<span className="text-xs text-muted">{run.status}</span></p>{run.error_message && <p className="mt-1 break-words text-xs text-red-800">{run.error_code ? `${run.error_code} · ` : ""}{run.error_message}</p>}<p className="mt-1 text-xs text-muted">{dateLabel(run.finished_at ?? run.started_at)}</p></div>)}</div> : <p className="text-sm text-muted">暂无运行记录。</p>}</Panel></section>
      </aside>
    </div>}
  </AppShell>;
}
