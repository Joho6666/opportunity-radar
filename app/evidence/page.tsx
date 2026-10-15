"use client";
import { EvidenceDetail, shortDate } from "@/components/evidence-detail";
import { useEvidenceQuery } from "@/lib/use-evidence-query";
import { BillingPanel } from "@/components/billing-panel";
import { CollectionControls } from "@/components/collection-controls";
import { DEFAULT_COLLECTION_POLICY, policyKey, validPolicy, type CollectionPolicy } from "@/lib/collection-policy";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, ChevronDown, FileJson, Loader2, RefreshCw, Search, Upload } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, DetailDrawer, EmptyState, PageHeader, Panel } from "@/components/ui";
import { cn } from "@/lib/utils";
import { useOpportunityStore } from "@/stores/use-opportunity-store";
import {
  EVIDENCE_CATEGORIES,
  BILLABLE_SOURCES,
  EVIDENCE_SOURCES,
  FEED_PRESETS,
  KEYWORD_PRESETS,
  SOURCE_LABELS,
  collectEvidence,
  collectionAttempt,
  fetchAcquisitionMetrics,
  convertEvidence,
  fetchEvidence,
  fetchEvidenceRuntime,
  exportEvidenceLabels,
  parseEvidenceImport,
  reviewEvidence,
  uploadEvidence,
  type EvidenceCategory,
  type EvidenceRecord,
  type EvidenceReviewInput,
  type EvidenceRuntime,
  type EvidenceSource,
  type CollectionAttempt,
  type AcquisitionMetrics,
} from "@/lib/evidence-client";
import {
  CATEGORY_LABELS,
  STATUS_FILTERS,
  countBy,
  evidenceBudgetLabel,
  gradeOf,
  sourceOf,
  sourcesIn,
  statusOf,
  visibleRecords,
  type ReviewStatus,
  type SortMode,
} from "@/lib/evidence-view";

type Toast = { message: string; href?: string; undo?: () => Promise<void> };

function isTyping(target: EventTarget | null) {
 const el=target as HTMLElement|null;return !!el&&(el.matches("input,textarea,select")||el.isContentEditable);
}
function EvidenceInbox() {
  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const {category,setCategory,status,setStatus,search,setSearch,sort,setSort,sourceFilter,setSourceFilter,selectedId,setSelectedId,ready:queryReady} = useEvidenceQuery();
  const [wide,setWide] = useState(false);
  useEffect(()=>{const media=matchMedia("(min-width: 1280px)");const sync=()=>setWide(media.matches);sync();media.addEventListener("change",sync);return ()=>media.removeEventListener("change",sync);},[]);
  const [convertingId, setConvertingId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [runtime, setRuntime] = useState<EvidenceRuntime | null>(null);
  const [metrics, setMetrics] = useState<AcquisitionMetrics | null>(null);
  const [billingRevision, setBillingRevision] = useState(0);
  const attemptRef = useRef<CollectionAttempt | null>(null);
  const [collectorOpen, setCollectorOpen] = useState(false);
  const [source, setSource] = useState<EvidenceSource>("rss");
  const [query, setQuery] = useState("");
  const [policy, setPolicy] = useState<CollectionPolicy>(DEFAULT_COLLECTION_POLICY);
  const [freshnessHours, setFreshnessHours] = useState(72);
  const configKey = policyKey(policy, freshnessHours);
  const configValid = validPolicy(policy) && Number.isInteger(freshnessHours) && freshnessHours >= 1 && freshnessHours <= 720;
  const [manualConfirmed, setManualConfirmed] = useState(false);
  useEffect(()=>{setManualConfirmed(false);},[source,query,configKey]);
  const [collecting, setCollecting] = useState(false);
  const [nextPage, setNextPage] = useState<{source: EvidenceSource; query: string; cursor: string; configKey: string} | null>(null);
  const [collectState, setCollectState] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importText, setImportText] = useState("");
  const [importState, setImportState] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recordsRef = useRef<EvidenceRecord[]>([]);
  useEffect(() => { recordsRef.current = records; }, [records]);

  const visible = useMemo(() => visibleRecords(records, { category, status, search, sort, source: sourceFilter, keep: convertingId }), [records, category, status, search, sort, sourceFilter, convertingId]);
  const sources = useMemo(() => sourcesIn(records, category), [records, category]);
  const counts = useMemo(() => Object.fromEntries(EVIDENCE_CATEGORIES.map((item) => [item, countBy(records, item)])) as Record<EvidenceCategory, ReturnType<typeof countBy>>, [records]);
  const selected = visible.find((record) => record.evidence_id === selectedId) ?? null;

  const showToast = useCallback((next: Toast | null) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToast(next);
    if (next) toastTimer.current = setTimeout(() => setToast(null), next.undo ? 8000 : 4000);
  }, []);
  const holdToast = () => { if (toastTimer.current) clearTimeout(toastTimer.current); };
  const releaseToast = () => { toastTimer.current = setTimeout(() => setToast(null), 3000); };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [groups, nextRuntime, nextMetrics] = await Promise.all([
        Promise.all(EVIDENCE_CATEGORIES.map((item) => fetchEvidence(item, 500))),
        fetchEvidenceRuntime(),
        fetchAcquisitionMetrics(),
      ]);
      const next = groups.flat();
      setRecords(next);
      setRuntime(nextRuntime);
      setMetrics(nextMetrics);
      
    } catch (reason) {
      setRecords([]);
      setMetrics(null);
      setError(reason instanceof Error ? reason.message : "加载证据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  useEffect(()=>{
    if (!queryReady || loading) return;
    if (selectedId && !selected) setSelectedId(wide ? visible[0]?.evidence_id ?? null : null, true);
  },[visible,selected,selectedId,queryReady,loading,wide,setSelectedId]);

  /** Replace one record in place; if it left the current view, select whatever took its slot. */
  const applyRecord = useCallback((updated: EvidenceRecord, keepBefore: string | null = convertingId, keepAfter: string | null = keepBefore) => {
    const current = recordsRef.current;
    const next = current.map((record) => record.evidence_id === updated.evidence_id ? { ...record, ...updated } : record);
    const options = { category, status, search, sort, source: sourceFilter };
    const before = visibleRecords(current, { ...options, keep: keepBefore });
    const after = visibleRecords(next, { ...options, keep: keepAfter });
    recordsRef.current = next;
    setRecords(next);
    if (!after.some((record) => record.evidence_id === updated.evidence_id)) {
      const index = before.findIndex((record) => record.evidence_id === updated.evidence_id);
      setSelectedId(after[Math.min(Math.max(index, 0), after.length - 1)]?.evidence_id ?? null);
    }
  }, [category, status, search, sort, sourceFilter, convertingId, setSelectedId]);

  const review = useCallback(async (record: EvidenceRecord, input: EvidenceReviewInput) => {
    const previous: ReviewStatus = statusOf(record);
    try {
      applyRecord(await reviewEvidence(record.evidence_id, input));
      if (input.verification_status && input.verification_status !== previous) {
        const label = input.verification_status === "verified" ? "已核实" : input.verification_status === "invalidated" ? "已排除" : "已退回待复核";
        showToast({
          message: `${label}：${record.raw_text.slice(0, 24)}${record.raw_text.length > 24 ? "…" : ""}`,
          undo: async () => { applyRecord(await reviewEvidence(record.evidence_id, { verification_status: previous })); showToast({ message: "已撤销" }); },
        });
      } else if (input.category) {
        showToast({ message: `已移到「${CATEGORY_LABELS[input.category]}」` });
      } else if (input.notes !== undefined) {
        showToast({ message: "备注已保存" });
      }
    } catch (reason) {
      showToast({ message: reason instanceof Error ? reason.message : "复核失败" });
    }
  }, [applyRecord, showToast]);

  const startConvert = useCallback(async (record: EvidenceRecord) => {
    // Pin the record first so verifying it does not pull it out of the pending view.
    setSelectedId(record.evidence_id);
    setConvertingId(record.evidence_id);
    if (statusOf(record) !== "verified") {
      try { applyRecord(await reviewEvidence(record.evidence_id, { verification_status: "verified" }), record.evidence_id); }
      catch (reason) { setConvertingId(null); showToast({ message: reason instanceof Error ? reason.message : "核实失败" }); }
    }
  }, [applyRecord, showToast, setSelectedId]);

  const convert = useCallback(async (record: EvidenceRecord, input: EvidenceReviewInput) => {
    try {
      const opportunity = await convertEvidence(record.evidence_id, input);
      const id = String(opportunity.id ?? "");
      setConvertingId(null);
      applyRecord({ ...record, verification_status: "verified", converted_opportunity_id: id }, record.evidence_id, null);
      void useOpportunityStore.getState().hydrate(true);
      showToast({ message: `已转为机会：${input.title}`, href: id ? `/opportunities/${id}` : "/opportunities" });
    } catch (reason) {
      showToast({ message: reason instanceof Error ? reason.message : "转换失败" });
    }
  }, [applyRecord, showToast]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "/" && !isTyping(event.target)) { event.preventDefault(); searchInput.current?.focus(); return; }
      if (isTyping(event.target) || convertingId) return;
      const index = visible.findIndex((record) => record.evidence_id === selectedId);
      const key = event.key.toLowerCase();
      if (key === "j" || event.key === "ArrowDown") { event.preventDefault(); setSelectedId(visible[Math.min(index + 1, visible.length - 1)]?.evidence_id ?? null); return; }
      if (key === "k" || event.key === "ArrowUp") { event.preventDefault(); setSelectedId(visible[Math.max(index - 1, 0)]?.evidence_id ?? null); return; }
      if (!selected) return;
      if (key === "v") void review(selected, { verification_status: "verified" });
      else if (key === "x") void review(selected, { verification_status: "invalidated" });
      else if (key === "u") void review(selected, { verification_status: "unverified" });
      else if (key === "o") window.open(selected.url, "_blank", "noreferrer");
      else if (key === "c" && selected.category === "buyer" && !selected.converted_opportunity_id) void startConvert(selected);
      else if (["1", "2", "3", "4", "5"].includes(key)) {
        const target = EVIDENCE_CATEGORIES[Number(key) - 1];
        if (target !== selected.category) void review(selected, { category: target });
      } else return;
      event.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, selected, selectedId, convertingId, review, startConvert, setSelectedId]);

  async function collect(cursor?: string) {
    if (!query.trim()) { setCollectState("请先填写搜索词"); return; }
    if (!configValid) { setCollectState("时间窗口需为1–720小时；每组最多20个词，每词最多100字；互动数需为有效整数。"); return; }
    setCollecting(true);
    setCollectState(null);
    try {
      const attempt = collectionAttempt(attemptRef.current,source,query,cursor,runtime?.billing_batch_id ?? undefined,configKey);
      attemptRef.current = attempt;
      const result = await collectEvidence(source, query.trim(), manualConfirmed, cursor, attempt.requestId,runtime?.billing_batch_id,{freshness_hours:freshnessHours,policy});
      attemptRef.current = null;
      setNextPage(result.next_cursor ? {source,query:query.trim(),cursor:result.next_cursor,configKey} : null);
      setSort(policy.sort);
      setManualConfirmed(false);
      setCollectState(`采集 ${result.fetched} 条，新增 ${result.inserted} 条，重复 ${result.duplicates} 条，过期 ${result.stale ?? 0} 条，时间未知过滤 ${result.filtered?.unknown_date ?? 0} 条，关键词过滤 ${result.filtered?.terms ?? 0} 条，活跃信号过滤 ${result.filtered?.activity ?? 0} 条，拒绝 ${result.rejected} 条`);
      await load();
    } catch (reason) {
      setCollectState(reason instanceof Error ? reason.message : "采集失败");
    } finally {
      setCollecting(false);
      setBillingRevision(value => value + 1);
      void fetchEvidenceRuntime().then(setRuntime).catch(() => setRuntime(null));
    }
  }

  async function importEvidence() {
    setImportState(null);
    setImporting(true);
    try {
      const items = parseEvidenceImport(importText);
      const result = await uploadEvidence(`frontend-${Date.now()}`, items);
      setImportText("");
      setImportState(`已新增 ${result.inserted} 条，重复 ${result.duplicates} 条`);
      setImportOpen(false);
      await load();
    } catch (reason) {
      setImportState(reason instanceof Error ? reason.message : "导入失败");
    } finally {
      setImporting(false);
    }
  }

  async function readFile(file: File) {
    setImportState(null);
    try { setImportText(await file.text()); setImportOpen(true); }
    catch { setImportState("无法读取该文件"); }
  }

  const billable = BILLABLE_SOURCES.has(source);
  const requestPrice = runtime?.sources[source]?.estimated_request_cost_usd;
  const paidBlocked = billable && (!manualConfirmed || !runtime?.paid_api_enabled || !requestPrice || (runtime.billing_batch && (!runtime.billing_batch.enabled || runtime.billing_batch.remaining_requests < 1 || runtime.billing_batch.remaining_cost_usd < requestPrice)));

  function renderDetail(record: EvidenceRecord) {return <EvidenceDetail key={record.evidence_id} record={record} selected converting={record.evidence_id===convertingId} onSelect={()=>undefined} onReview={input=>review(record,input)} onStartConvert={()=>void startConvert(record)} onCancelConvert={()=>{setConvertingId(null);const left=recordsRef.current.find(item=>item.evidence_id===record.evidence_id);if(left)applyRecord(left,record.evidence_id,null);}} onConvert={input=>convert(record,input)}/>;}

  return (
    <>
      <PageHeader
        title="证据收件箱"
        compact
        action={<div className="flex flex-wrap gap-2">
          <Button variant="secondary" className="whitespace-nowrap" onClick={() => setCollectorOpen((value) => !value)}><Search size={15} /> 采集</Button>
          <Button variant="secondary" className="whitespace-nowrap" onClick={() => setImportOpen((value) => !value)}><Upload size={15} /> 导入</Button>
          <Button variant="secondary" onClick={()=>void exportEvidenceLabels().then(result=>{const href=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=href;a.download="reviewed-labels.json";a.click();URL.revokeObjectURL(href);showToast({message:`已导出 ${result.count} 条人工标注，目标 ${result.target} 条`});}).catch(e=>showToast({message:e instanceof Error ? e.message : "导出失败"}))}>导出标注</Button>
          <Button variant="ghost" onClick={() => void load()} disabled={loading} aria-label="刷新"><RefreshCw size={15} className={loading ? "animate-spin" : ""} /></Button>
        </div>}
      />

      <details className="mb-2 rounded-md border border-line bg-white text-xs text-muted"><summary className="flex min-h-9 flex-wrap items-center gap-2 px-3 py-2"><span className="font-medium text-mist">费用与来源统计</span><span>· {runtime ? runtime.paid_api_enabled ? "付费需逐次确认" : "真实付费已关闭" : "费用状态加载中"}</span>{runtime?.billing_batch && <span>· 本轮剩余 {runtime.billing_batch.remaining_requests} 次 / US${runtime.billing_batch.remaining_cost_usd.toFixed(2)}</span>}<ChevronDown size={14} className="ml-auto"/></summary><div className="space-y-3 border-t border-line p-3">      <BillingPanel refreshKey={billingRevision} />
      {metrics && <Panel className="overflow-x-auto p-4"><h2 className="mb-2 font-semibold">来源获客漏斗</h2>{Object.keys(metrics.source_yield).length ? <table className="w-full text-left text-xs"><thead><tr className="text-muted"><th className="p-2">来源</th><th className="p-2">采集</th><th className="p-2">唯一证据</th><th className="p-2">买方候选</th><th className="p-2">人工核实买方</th></tr></thead><tbody>{Object.entries(metrics.source_yield).map(([name,row]) => <tr key={name} className="border-t border-line"><td className="p-2">{SOURCE_LABELS[name as EvidenceSource] ?? name}</td><td className="p-2">{row.collected}</td><td className="p-2">{row.evidence}</td><td className="p-2">{row.buyer}</td><td className="p-2">{row.verified_buyer}</td></tr>)}</tbody></table> : <p className="text-sm text-muted">暂无数据</p>}<p className="mt-2 text-xs text-muted">买方候选是分类判断，人工核实由你查看公开原文后记录。</p></Panel>}
      {runtime?.warning && <p className="mb-4 rounded-md border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-900">{runtime.warning}</p>}

</div></details>

      {collectorOpen && <Panel className="mb-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-mist">手动采集 <span className="ml-1 text-xs font-normal text-muted">每次只取一页；下一页需要再次确认</span></p>
          <button className="text-muted hover:text-mist" onClick={() => setCollectorOpen(false)} aria-label="收起采集"><ChevronDown size={18} /></button>
        </div>
        <form className="mt-3 grid gap-2 md:grid-cols-[160px_1fr_auto]" onSubmit={(event) => { event.preventDefault(); void collect(); }}>
          <select value={source} onChange={(event) => setSource(event.target.value as EvidenceSource)} className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-mist" aria-label="数据源">
            {EVIDENCE_SOURCES.map((item) => <option key={item} value={item} disabled={runtime ? !runtime.sources[item]?.configured : false}>{SOURCE_LABELS[item]}{BILLABLE_SOURCES.has(item) ? " · 收费" : ""}{runtime && !runtime.sources[item]?.configured ? "（未配置）" : ""}</option>)}
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value.slice(0, 200))} placeholder={source === "rss" ? "RSS 地址，或点下面的预设" : "搜索词，回车开始；问句更容易搜到买家，如「有人接剪辑吗」"} aria-label="搜索词" className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-mist outline-none focus:border-ai" />
          <Button type="submit" disabled={collecting || !configValid || !runtime?.sources[source]?.configured || !!paidBlocked}>{collecting && <Loader2 size={15} className="animate-spin" />}{collecting ? "采集中…" : "开始采集"}</Button>
        </form>
        {source === "rss" && <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">免费预设：{FEED_PRESETS.map((preset) => <button key={preset.url} type="button" onClick={() => setQuery(preset.url)} className={cn("rounded border px-2 py-0.5 transition", query === preset.url ? "border-ai/60 text-indigo-800" : "border-line hover:text-mist")}>{preset.label}</button>)}</div>}
        {["个人文档","企业视频与开发"].map(group => <div key={group} className="mt-2 flex flex-wrap gap-2 text-xs text-muted"><span>{group}：</span>{KEYWORD_PRESETS.filter(x => x.group === group).map(preset => <button type="button" key={preset.query} className="rounded border border-line px-2 py-1 hover:text-mist" onClick={() => {setSource(preset.source);setQuery(preset.query);setManualConfirmed(false);}}>{preset.query}</button>)}</div>)}
        <CollectionControls policy={policy} onChange={next=>{setPolicy(next);setManualConfirmed(false);}} hours={freshnessHours} onHours={hours=>{setFreshnessHours(hours);setManualConfirmed(false);}} disabled={collecting}/>
        <p className="mt-2 text-xs text-muted">{source === "rss" ? "RSS只读取所选订阅源，包含词在原文中筛选；不是全网关键词搜索。" : "筛选范围受平台实际返回结果限制；热门排序只比较本次已取得的帖子。"}{["douyin","xiaohongshu"].includes(source) ? "当前国内搜索端点上游固定近一周，放宽本地时间窗口不会扩展上游范围；真实接口仍待验证。" : ""}</p>
        {billable && <p className="mt-2 text-xs text-amber-900">{requestPrice ? `此接口已核实单价 $${requestPrice.toFixed(4)} / 次；单击仅取一页。` : "接口价格未核实，付费采集被阻止。"}</p>}
        {runtime?.sources[source]?.validation_status && <p className="mt-2 text-xs text-muted">来源验证：{({contract_only:"离线契约通过；尚未实采验证",response_compatible:"已存真实响应可解析；分页与业务效果仍需核实",response_incompatible:"已存响应解析不兼容"} as Record<string,string>)[runtime.sources[source].validation_status ?? ""] ?? runtime.sources[source].validation_status}</p>}
        {runtime?.sources[source]?.pricing_evidence && <p className="mt-1 text-xs text-muted">价格依据：<a href={runtime.sources[source].pricing_evidence?.source_url} target="_blank" rel="noreferrer" className="underline">官方来源</a> · 核实 {shortDate(runtime.sources[source].pricing_evidence?.verified_at)}</p>}
        {billable && <label className="mt-2 flex items-center gap-2 text-xs text-amber-900"><input type="checkbox" checked={manualConfirmed} onChange={(event) => setManualConfirmed(event.target.checked)} />该来源按调用收费，我确认本次采集</label>}
        {nextPage && nextPage.source === source && nextPage.query === query.trim() && nextPage.configKey === configKey && <Button className="mt-3" variant="secondary" disabled={collecting || !configValid || !!paidBlocked} onClick={() => void collect(nextPage.cursor)}>采集下一页（独立请求）</Button>}
        {collectState && <p className="mt-2 text-sm text-muted">{collectState}</p>}
        {collectState && attemptRef.current && <Button className="mt-2" variant="secondary" onClick={() => {attemptRef.current=null;setManualConfirmed(false);setCollectState("已准备新的请求；如需付费，请重新确认，新的调用会占用额度。");}}>准备新的采集请求</Button>}
      </Panel>}

      {importOpen && <Panel className="mb-4 p-4">
        <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><FileJson size={16} className="text-indigo-700" /><p className="text-sm font-medium text-mist">导入证据 JSON <span className="ml-1 text-xs font-normal text-muted">支持证据数组，导入后去重，原文不改写</span></p></div><button className="text-muted hover:text-mist" onClick={() => setImportOpen(false)} aria-label="关闭导入"><ChevronDown size={18} /></button></div>
        <textarea value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='[{"source":"tikhub","url":"https://...","raw_text":"...","category":"market"}]' className="mt-3 min-h-28 w-full rounded-lg border border-line bg-ink p-3 font-mono text-xs text-slate-800 outline-none focus:border-ai" aria-label="Evidence JSON" />
        <div className="mt-2 flex flex-wrap items-center gap-3"><input ref={fileInput} type="file" accept="application/json,.json" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void readFile(file); }} /><Button variant="secondary" onClick={() => fileInput.current?.click()} disabled={importing}><Upload size={15} /> 读取文件</Button><Button onClick={() => void importEvidence()} disabled={!importText.trim() || importing}>{importing && <Loader2 size={15} className="animate-spin" />}{importing ? "导入中…" : "提交导入"}</Button>{importState && <span className="text-sm text-muted">{importState}</span>}</div>
      </Panel>}

      <div role="group" aria-label="证据分类" className="mb-2 flex flex-wrap gap-1 border-b border-line pb-2">{EVIDENCE_CATEGORIES.map(item=><button key={item} aria-pressed={category===item} onClick={()=>{setCategory(item);setSourceFilter(null);}} className={cn("min-h-10 rounded-md px-3 text-sm transition-colors",category===item?"bg-indigo-50 font-medium text-ai":"text-muted hover:bg-white")}>{CATEGORY_LABELS[item]} <span className="mono text-xs">{loading?"…":counts[item].all}</span></button>)}</div>

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="flex rounded-md border border-line bg-panel/60 p-0.5" role="group" aria-label="复核状态">
          {STATUS_FILTERS.map((item) => (
            <button key={item.value} onClick={() => setStatus(item.value)} aria-pressed={status === item.value} className={cn("rounded px-2.5 py-1 text-xs transition", status === item.value ? "bg-indigo-50 text-ai" : "text-muted hover:text-mist")}>
              {item.label} <span className="mono opacity-70">{counts[category][item.value]}</span>
            </button>
          ))}
        </div>
        <label className="relative min-w-48 flex-1">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input ref={searchInput} value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { setSearch(""); event.currentTarget.blur(); } }} placeholder="在当前分类里搜索原文或备注" aria-label="搜索证据" className="h-8 w-full rounded-md border border-line bg-panel/60 pl-8 pr-8 text-xs text-mist outline-none focus:border-ai" />
          <span className="absolute right-2 top-1/2 -translate-y-1/2"><span className="text-xs text-muted">/</span></span>
        </label>
        <select aria-label="按来源筛选" value={sourceFilter??""} onChange={e=>setSourceFilter(e.target.value||null)} className="rounded-md border border-line px-2 text-xs"><option value="">全部来源</option>{sources.map(item=><option key={item.key} value={item.key}>{item.label} ({item.count})</option>)}</select>
        <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)} aria-label="排序" className="h-8 rounded-md border border-line bg-panel/60 px-2 text-xs text-mist">
          <option value="lead">获客分数优先</option>
          <option value="hot">热度优先（已采集）</option>
          <option value="grade">等级优先</option>
          <option value="latest">最新优先</option>
        </select>
      </div>
      {loading && <Panel className="flex items-center justify-center gap-2 p-10 text-sm text-muted"><Loader2 className="animate-spin" size={18} /> 正在加载证据…</Panel>}
      {!loading && error && <Panel className="border-red-400/30 p-6"><div className="flex items-start gap-3 text-red-700"><AlertCircle size={19} className="mt-0.5 shrink-0" /><div><p className="font-medium">加载失败</p><p className="mt-1 text-sm text-red-700/80">{error}</p><Button className="mt-4" variant="secondary" onClick={() => void load()}>重试</Button></div></div></Panel>}
      {!loading && !error && visible.length === 0 && (
        counts[category].all > 0 && status === "pending" && !search
          ? <EmptyState title={`「${CATEGORY_LABELS[category]}」已全部复核完 🎉`}><p className="text-sm text-muted">核实 {counts[category].verified} 条，排除 {counts[category].invalidated} 条。</p><Button className="mt-4" variant="secondary" onClick={() => setStatus("verified")}>查看已核实</Button></EmptyState>
          : <EmptyState title={search ? `没有匹配「${search}」的证据` : `还没有${CATEGORY_LABELS[category]}`}>{!search && <><p className="text-sm text-muted">可以先采集一次，或者导入一批真实来源数据。</p><Button className="mt-4" onClick={() => setCollectorOpen(true)}>开始采集</Button></>}</EmptyState>
      )}
      {!loading && !error && visible.length > 0 && <div className="grid items-start gap-0 overflow-hidden rounded-lg border border-line bg-white xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0"><div className="flex min-h-9 items-center justify-between border-b border-line bg-slate-50 px-4 text-xs text-muted"><span>{visible.length} 条候选 · 选择查看依据</span><span>预测分数 ≠ 成交概率</span></div><div className="divide-y divide-line">{visible.map(record=><button key={record.evidence_id} id={`evidence-${record.evidence_id}`} data-evidence-row type="button" aria-pressed={selectedId===record.evidence_id} onClick={()=>setSelectedId(record.evidence_id)} className={cn("block w-full border-l-2 px-4 py-3 text-left transition-colors",record.evidence_id===selectedId?"border-ai bg-indigo-50/60":"border-transparent hover:bg-slate-50")}><div className="flex items-start justify-between gap-3"><p className="line-clamp-2 text-sm font-medium leading-6">{record.raw_text.split("\n").find(Boolean)?.slice(0,180)}</p><span className="mono shrink-0 rounded bg-ink px-2 py-1 text-xs text-ai" title="获客优先级预测分数">{record.ranking?.lead_score ?? "未知"}<span className="ml-1 text-muted">分</span></span></div><div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted"><span>{sourceOf(record).label}</span><span>{shortDate(record.ranking?.signals.published_at ?? record.published_at) ?? "发布时间未知"}</span><span>{evidenceBudgetLabel(record)}</span><span>证据 {gradeOf(record)}</span><span className={statusOf(record)==="verified"?"text-signal":"text-amber-800"}>{statusOf(record)==="verified"?"人工已核实":statusOf(record)==="invalidated"?"已排除":"待复核"}</span></div></button>)}</div></div>
        <aside aria-label="证据详情" className="sticky top-20 hidden max-h-[calc(100vh-100px)] overflow-y-auto border-l border-line xl:block">{selected ? renderDetail(selected) : <div className="p-8 text-center text-sm text-muted">选择一条线索，查看原文和核实依据。</div>}</aside>
      </div>}
      <DetailDrawer open={!wide&&!!selected} title="证据详情" onClose={()=>{setConvertingId(null);setSelectedId(null);}}>{selected&&renderDetail(selected)}</DetailDrawer>

      {toast && (
        <div role="status" onMouseEnter={holdToast} onMouseLeave={releaseToast} className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-line bg-panel px-4 py-2.5 text-sm text-mist shadow-xl">
          <span className="max-w-[60vw] truncate">{toast.message}</span>
          {toast.href && <Link href={toast.href} className="text-signal hover:underline">查看</Link>}
          {toast.undo && <button className="font-medium text-indigo-700 hover:text-mist" onClick={() => { const undo = toast.undo; showToast(null); void undo?.(); }}>撤销</button>}
        </div>
      )}
    </>
  );
}

export default function Page() { return <AppShell><EvidenceInbox /></AppShell>; }
