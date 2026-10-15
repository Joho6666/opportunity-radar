"use client";
import Link from "next/link";
import { useState } from "react";
import { useParams } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { Button, PageHeader, Panel, MetricCard } from "@/components/ui";
import { CollectionControls } from "@/components/collection-controls";
import { DEFAULT_COLLECTION_POLICY, splitTerms, validPolicy, type CollectionPolicy } from "@/lib/collection-policy";
import { BILLABLE_SOURCES, SOURCE_LABELS, type EvidenceSource } from "@/lib/evidence-client";
import { isRadarEnabled } from "@/lib/radar-status";
import { updateRadarCollection } from "@/services/radar.service";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
import type { Radar } from "@/types/domain";

function EditCollection({ radar, onClose }: {radar:Radar;onClose:()=>void}) {
  const [keywords,setKeywords] = useState(radar.keywords.join("，"));
  const [hours,setHours] = useState(radar.freshnessHours ?? 72);
  const [budget,setBudget] = useState(radar.minimumBudget);
  const [policy,setPolicy] = useState<CollectionPolicy>(radar.collectionPolicy ?? {...DEFAULT_COLLECTION_POLICY,time_basis:"activity",include_unknown_dates:true});
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const hydrate = useOpportunityStore(s=>s.hydrate);
  async function save() {
    setBusy(true);setError("");
    try { await updateRadarCollection(radar,{keywords:splitTerms(keywords),freshnessHours:hours,collectionPolicy:policy,minimumBudget:budget});await hydrate(true);onClose(); }
    catch(e) {setError(e instanceof Error ? e.message : "保存失败");}
    finally {setBusy(false);}
  }
  return <Panel className="mt-5 p-5"><h2 className="font-semibold">编辑采集配置</h2>
    <label className="mt-3 block text-sm text-muted">搜索关键词（逗号分隔，每项单独查询）<input aria-label="雷达搜索关键词" className="mt-1 w-full rounded border border-line bg-ink p-2 text-mist" value={keywords} onChange={e=>setKeywords(e.target.value)}/></label>
    <label className="mt-3 block text-sm text-muted">最低预算（元，未知预算仍待核实）<input aria-label="雷达最低预算" type="number" min="0" className="ml-2 rounded border border-line bg-ink p-2 text-mist" value={budget} onChange={e=>setBudget(Number(e.target.value))}/></label>
    <CollectionControls policy={policy} onChange={setPolicy} hours={hours} onHours={setHours} disabled={busy}/>
    {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
    <div className="mt-4 flex gap-2"><Button disabled={busy || !validPolicy(policy) || !Number.isInteger(hours) || hours<1 || hours>720 || !Number.isInteger(budget) || budget<0 || !splitTerms(keywords).length} onClick={()=>void save()}>{busy ? "保存中…" : "保存采集配置"}</Button><Button variant="secondary" disabled={busy} onClick={onClose}>取消</Button></div>
  </Panel>;
}

export default function RadarDetail() {
  const { id } = useParams<{id:string}>();
  const radar = useOpportunityStore(s=>s.radars.find(r=>r.id===id));
  const toggle = useOpportunityStore(s=>s.toggleRadar);
  const runNow = useOpportunityStore(s=>s.runRadarNow);
  const loading = useOpportunityStore(s=>s.loading);
  const hydrated = useOpportunityStore(s=>s.hydrated);
  const loadError = useOpportunityStore(s=>s.error);
  const [editing,setEditing] = useState(false);
  const [error,setError] = useState("");
  if (!radar) return <AppShell><PageHeader title={loadError?"雷达加载失败":loading||!hydrated?"加载雷达…":"雷达不存在"}/></AppShell>;
  const policy = radar.collectionPolicy;
  const paid = radar.sources.some(s=>BILLABLE_SOURCES.has(s as EvidenceSource));
  async function action(operation:()=>Promise<void>) {
    setError("");try {await operation();}catch(e) {setError(e instanceof Error ? e.message : "操作失败");}
  }
  return <AppShell>
    <PageHeader title={radar.name} description={radar.goal} action={<div className="flex flex-wrap gap-2"><Button variant="secondary" disabled={loading} onClick={()=>setEditing(x=>!x)}>编辑配置</Button><Button variant="secondary" disabled={loading} onClick={()=>void action(()=>toggle(id))}>{isRadarEnabled(radar.status) ? "暂停" : "恢复"}</Button><Button disabled={loading || radar.status==="running" || paid} onClick={()=>void action(()=>runNow(id))}>立即搜索</Button></div>}/>
    {error && <p role="alert" className="mb-4 text-sm text-red-700">{error}</p>}
    {paid && <p className="mb-4 text-sm text-amber-900">付费源需在<Link className="underline" href="/evidence">证据收件箱</Link>逐页确认并通过价格、授权与预算检查。此处不触发付费采集。</p>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[["最近运行扫描",radar.stats.scanned],["发现机会",radar.stats.found],["与你匹配",radar.stats.matched],["强烈推荐",radar.stats.recommended]].map(([label,value])=><MetricCard key={String(label)} label={String(label)} value={Number(value)}/>)}</div>
    {editing && <EditCollection key={radar.id} radar={radar} onClose={()=>setEditing(false)}/>}
    <div className="mt-6 grid gap-5 lg:grid-cols-2"><Panel className="p-5"><h2 className="font-semibold">已保存采集条件</h2><div className="mt-4 flex flex-wrap gap-2">{radar.keywords.map(x=><span className="rounded-full border border-line px-3 py-1 text-sm" key={x}>{x}</span>)}</div>
      <p className="mt-4 text-sm text-muted">来源：{radar.sources.map(s=>SOURCE_LABELS[s as EvidenceSource] ?? s).join("、")} · 地区偏好：{radar.locations.join("、") || "不限"}</p>
      <p className="mt-2 text-sm text-muted">最近 {radar.freshnessHours ?? 72} 小时 · {(policy?.time_basis ?? "activity")==="published" ? "原帖发布时间" : "来源更新时间"} · {policy?.include_unknown_dates===false ? "过滤时间未知" : "保留时间未知"} · 最低预算 ¥{radar.minimumBudget}</p>
      <p className="mt-2 text-sm text-muted">包含词：{policy?.required_terms.join("、") || "不限"} · {policy?.match_mode==="all" ? "全部命中" : "任意命中"} · 排除：{policy?.excluded_terms.join("、") || "无"}</p>
      <p className="mt-2 text-sm text-muted">公开活跃信号：{({any:"不限",author:"窗口内有作者",discussion:"窗口内有作者及评论"})[policy?.activity_filter ?? "any"]} · 互动至少 {policy?.min_interactions ?? 0} · {policy?.sort==="hot" ? "已采集结果热度优先" : "最新优先"}</p>
      <p className="mt-2 text-xs text-muted">作者和互动仅作公开信号，真人身份需核实；地区偏好不代表平台已按地区过滤。逐帖评分和依据见证据收件箱。</p>
    </Panel><Panel className="p-5"><h2 className="font-semibold">最近实际查询</h2>{radar.queries?.length ? <ul className="mono mt-4 space-y-2 text-sm text-indigo-800">{radar.queries.map((q,i)=><li key={i}>{q.source}：{q.query}</li>)}</ul> : <p className="mt-4 text-sm text-muted">尚无查询记录；首次运行后显示实际提交的查询。</p>}<p className="mt-4 text-xs text-muted">最后运行：{radar.lastRunAt} · 下次运行：{radar.nextRunAt}</p><Link href="/evidence" className="mt-4 inline-block text-sm text-indigo-700 underline">查看采集帖子与评分</Link></Panel></div>
  </AppShell>;
}
