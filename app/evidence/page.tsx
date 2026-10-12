"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, ChevronDown, ExternalLink, FileJson, Loader2, RefreshCw, Upload } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, EmptyState, PageHeader, Panel } from "@/components/ui";
import {
  EVIDENCE_CATEGORIES,
  EVIDENCE_SOURCES,
  collectEvidence,
  fetchEvidence,
  fetchEvidenceRuntime,
  parseEvidenceImport,
  uploadEvidence,
  type EvidenceCategory,
  type EvidenceRecord,
  type EvidenceRuntime,
  type EvidenceSource,
} from "@/lib/evidence-client";

const labels: Record<EvidenceCategory, string> = {
  buyer: "潜在购买需求",
  content: "内容问题",
  market: "市场变化",
};

const descriptions: Record<EvidenceCategory, string> = {
  buyer: "原文出现找人、预算、报价或交付意图的候选信号。",
  content: "适合转成教程、选题或服务内容的问题。",
  market: "竞品案例、平台变化、广告趋势和供给侧信息。",
};

function classificationLabel(record: EvidenceRecord) {
  if (record.classification_source === "rule_v1") return "规则分类";
  if (record.classification_source === "manual") return "人工分类";
  return "未分类";
}

function formatDate(value: string | null) {
  if (!value) return "未提供";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function formatEngagement(record: EvidenceRecord) {
  const raw = record.metadata?.engagement;
  if (!raw) return null;
  try {
    const value = typeof raw === "string" ? JSON.parse(raw) as Record<string, unknown> : raw as Record<string, unknown>;
    const labels: Record<string, string> = { plays: "播放", likes: "点赞", comments: "评论", shares: "分享" };
    return Object.entries(labels)
      .filter(([key]) => value[key] !== undefined && value[key] !== null)
      .map(([key, label]) => `${label} ${Number(value[key]).toLocaleString("zh-CN")}`)
      .join(" · ");
  } catch {
    return null;
  }
}

function EvidenceCard({ record }: { record: EvidenceRecord }) {
  const engagement = formatEngagement(record);
  return (
    <article className="rounded-xl border border-line bg-panel/80 p-5 transition hover:border-indigo-400/40 hover:bg-panel">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-indigo-400/10 px-2.5 py-1 text-xs font-medium text-indigo-200">{labels[record.category]}</span>
            <span className="rounded-full bg-amber-400/10 px-2.5 py-1 text-xs text-amber-200">未核实</span>
            <span className="rounded-full border border-line px-2.5 py-1 text-xs text-muted">{classificationLabel(record)}</span>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-medium text-mist">{record.source_platform || record.source}</span>
            {record.acquisition_tool && <span className="text-xs text-muted">采集：{record.acquisition_tool}</span>}
          </div>
        </div>
        <a className="inline-flex shrink-0 items-center gap-1.5 rounded border border-line px-3 py-2 text-xs text-indigo-200 transition hover:border-indigo-300 hover:text-white" href={record.url} target="_blank" rel="noreferrer">
          查看原文 <ExternalLink size={13} />
        </a>
      </div>

      <p className="mt-4 text-[15px] leading-7 text-slate-200">{record.raw_text}</p>

      <div className="mt-5 grid gap-3 border-t border-line pt-4 text-xs sm:grid-cols-2 lg:grid-cols-4">
        <div><p className="text-muted">分类理由</p><p className="mt-1 text-slate-300">{record.classification_reason || "未记录"}</p></div>
        <div><p className="text-muted">发布时间</p><p className="mt-1 text-slate-300">{formatDate(record.published_at)}</p></div>
        <div><p className="text-muted">采集时间</p><p className="mt-1 text-slate-300">{formatDate(record.captured_at)}</p></div>
        <div><p className="text-muted">付款信号</p><p className="mt-1 text-signal">{record.payment_signal ?? "未发现"}</p></div>
      </div>
      {engagement && <p className="mt-3 text-xs text-muted">互动数据：<span className="text-slate-300">{engagement}</span></p>}
    </article>
  );
}

function EvidenceInbox() {
  const [category, setCategory] = useState<EvidenceCategory>("market");
  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [importState, setImportState] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [runtime, setRuntime] = useState<EvidenceRuntime | null>(null);
  const [source, setSource] = useState<EvidenceSource>("github");
  const [query, setQuery] = useState("");
  const [manualConfirmed, setManualConfirmed] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectState, setCollectState] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextRecords, nextRuntime] = await Promise.all([
        Promise.all(EVIDENCE_CATEGORIES.map((item) => fetchEvidence(item, 500))).then((groups) => groups.flat()),
        fetchEvidenceRuntime(),
      ]);
      setRecords(nextRecords);
      setRuntime(nextRuntime);
    }
    catch (reason) { setRecords([]); setError(reason instanceof Error ? reason.message : "加载证据失败"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function collect() {
    if (!query.trim()) { setCollectState("请先填写搜索词"); return; }
    setCollecting(true); setCollectState(null);
    try {
      const result = await collectEvidence(source, query.trim(), manualConfirmed);
      setCollectState(`采集 ${result.fetched} 条，新增 ${result.inserted} 条，重复 ${result.duplicates} 条，拒绝 ${result.rejected} 条`);
      await load();
    } catch (reason) { setCollectState(reason instanceof Error ? reason.message : "采集失败"); }
    finally { setCollecting(false); }
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
    } catch (reason) { setImportState(reason instanceof Error ? reason.message : "导入失败"); }
    finally { setImporting(false); }
  }

  async function readFile(file: File) {
    setImportState(null);
    try { setImportText(await file.text()); setImportOpen(true); }
    catch { setImportState("无法读取该文件"); }
  }

  return (
    <>
      <PageHeader
        title="证据收件箱"
        description="先收集事实，再人工判断是否值得行动。所有自动分类默认未核实。"
        action={<div className="flex gap-2"><Button variant="secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={15} className={loading ? "animate-spin" : ""} /> 刷新</Button><Button onClick={() => setImportOpen((value) => !value)}><Upload size={15} /> 导入</Button></div>}
      />

      {runtime?.warning && <Panel className="mb-5 border-amber-400/30 p-4 text-sm text-amber-100">{runtime.warning}</Panel>}
      <Panel className="mb-5 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-medium text-mist">手动采集真实来源</h2><p className="mt-1 text-xs text-muted">只运行一次搜索，不自动翻页；结果会保留原文并去重。</p></div><span className="text-xs text-muted">{runtime ? `存储：${runtime.storage_mode === "memory" ? "内存" : "PostgreSQL"}` : "正在读取运行状态…"}</span></div>
        <div className="mt-4 grid gap-3 md:grid-cols-[170px_1fr_auto]">
          <select value={source} onChange={(event) => setSource(event.target.value as EvidenceSource)} className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-mist">
            {EVIDENCE_SOURCES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value.slice(0, 200))} maxLength={200} placeholder="输入搜索词" className="rounded-lg border border-line bg-ink px-3 py-2 text-sm text-mist outline-none focus:border-indigo-400" />
          <Button onClick={() => void collect()} disabled={collecting || !runtime?.sources[source]?.configured || (source === "tikhub" || source === "web_search") && !manualConfirmed}>{collecting && <Loader2 size={15} className="animate-spin" />}{collecting ? "采集中…" : "开始采集"}</Button>
        </div>
        {(source === "tikhub" || source === "web_search") && <label className="mt-3 flex items-center gap-2 text-xs text-amber-100"><input type="checkbox" checked={manualConfirmed} onChange={(event) => setManualConfirmed(event.target.checked)} />我确认该来源可能产生费用，并授权本次采集</label>}
        {runtime && !runtime.sources[source]?.configured && <p className="mt-2 text-xs text-amber-200">该来源未配置，已禁用采集。</p>}
        {collectState && <p className="mt-3 text-sm text-muted">{collectState}</p>}
      </Panel>

      <div className="mb-5 grid gap-3 sm:grid-cols-3">
        {EVIDENCE_CATEGORIES.map((item) => <button key={item} role="tab" aria-selected={category === item} onClick={() => setCategory(item)} className={`rounded-xl border p-4 text-left transition ${category === item ? "border-indigo-400/60 bg-indigo-400/10" : "border-line bg-panel/60 hover:border-slate-500"}`}>
          <p className={`text-sm font-medium ${category === item ? "text-indigo-200" : "text-mist"}`}>{labels[item]}</p>
          <p className="mt-1 text-xs leading-5 text-muted">{descriptions[item]}</p>
        </button>)}
      </div>

      {importOpen && <Panel className="mb-5 p-5">
        <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><FileJson size={17} className="text-indigo-300" /><h2 className="font-medium text-mist">导入证据 JSON</h2></div><button className="text-muted hover:text-white" onClick={() => setImportOpen(false)} aria-label="关闭导入"><ChevronDown size={18} /></button></div>
        <p className="mt-1 text-xs text-muted">支持证据数组。导入后会去重，原文不会被改写。</p>
        <textarea value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='[{"source":"tikhub","url":"https://...","raw_text":"...","category":"market"}]' className="mt-4 min-h-32 w-full rounded-lg border border-line bg-ink p-3 font-mono text-xs text-slate-200 outline-none focus:border-indigo-400" aria-label="Evidence JSON" />
        <div className="mt-3 flex flex-wrap items-center gap-3"><input ref={fileInput} type="file" accept="application/json,.json" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void readFile(file); }} /><Button variant="secondary" onClick={() => fileInput.current?.click()} disabled={importing}><Upload size={15} /> 读取文件</Button><Button onClick={() => void importEvidence()} disabled={!importText.trim() || importing}>{importing && <Loader2 size={15} className="animate-spin" />}{importing ? "导入中…" : "提交导入"}</Button>{importState && <span className="text-sm text-muted">{importState}</span>}</div>
      </Panel>}

      {(() => { const visible = records.filter((record) => record.category === category); return <div className="mb-4 flex items-center justify-between"><div><h2 className="text-lg font-semibold text-mist">{labels[category]}</h2><p className="mt-1 text-xs text-muted">{loading ? "正在加载…" : `${visible.length} 条记录（已加载全部分类）`}</p></div><span className="rounded-full border border-line px-3 py-1 text-xs text-muted">默认仅供复核</span></div>; })()}
      {loading && <Panel className="flex items-center justify-center gap-2 p-10 text-sm text-muted"><Loader2 className="animate-spin" size={18} /> 正在加载证据…</Panel>}
      {!loading && error && <Panel className="border-red-400/30 p-6"><div className="flex items-start gap-3 text-red-200"><AlertCircle size={19} className="mt-0.5 shrink-0" /><div><p className="font-medium">加载失败</p><p className="mt-1 text-sm text-red-200/80">{error}</p><Button className="mt-4" variant="secondary" onClick={() => void load()}>重试</Button></div></div></Panel>}
      {!loading && !error && records.filter((record) => record.category === category).length === 0 && <EmptyState title={`还没有${labels[category]}`}><p className="text-sm text-muted">可以先运行一个雷达，或者导入一批真实来源数据。</p><Button className="mt-5" onClick={() => setImportOpen(true)}>导入第一批证据</Button></EmptyState>}
      {!loading && !error && records.filter((record) => record.category === category).length > 0 && <div className="space-y-4">{records.filter((record) => record.category === category).map((record) => <EvidenceCard key={record.evidence_id} record={record} />)}</div>}
    </>
  );
}

export default function Page() { return <AppShell><EvidenceInbox /></AppShell>; }