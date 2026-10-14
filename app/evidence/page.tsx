"use client";
import { BillingPanel } from "@/components/billing-panel";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertCircle, ArrowRight, Check, ChevronDown, ExternalLink, FileJson, Loader2, RefreshCw, RotateCcw, Search, Upload, X } from "lucide-react";
import { AppShell } from "@/components/app-shell";
import { Button, EmptyState, PageHeader, Panel } from "@/components/ui";
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
  STATUS_META,
  authorOf,
  countBy,
  draftOpportunity,
  evidenceBudgetLabel,
  gradeOf,
  parseBudget,
  reasonLabel,
  sourceOf,
  sourcesIn,
  statusOf,
  visibleRecords,
  type ReviewStatus,
  type SortMode,
  type StatusFilter,
} from "@/lib/evidence-view";

const descriptions: Record<EvidenceCategory, string> = {
  buyer: "有人想找人、给预算或要交付，值得优先看。",
  seller: "服务商推广与广告，不作为客户需求。",
  job: "招聘与求职信息，独立于项目客户。",
  content: "受众在提问或求教程，适合做内容。",
  market: "案例与趋势，了解行情用。",
};

const GRADE_TONE = {
  A: "border-signal/50 bg-signal/10 text-signal",
  B: "border-ai/50 bg-ai/10 text-indigo-200",
  C: "border-line bg-ink/60 text-muted",
};

type Toast = { message: string; href?: string; undo?: () => Promise<void> };

function shortDate(value: string | null | undefined) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function engagementOf(record: EvidenceRecord): string | null {
  const raw = record.metadata?.engagement;
  if (!raw) return null;
  try {
    // Older collectors stored a Python repr ("{'likes': 1, 'plays': None}").
    const value = (typeof raw === "string" ? JSON.parse(raw.replace(/'/g, '"').replace(/\bNone\b/g, "null")) : raw) as Record<string, unknown>;
    const labels: Record<string, string> = { plays: "播放", likes: "点赞", comments: "评论", shares: "分享" };
    const parts = Object.entries(labels)
      .filter(([key]) => typeof value[key] === "number" && (value[key] as number) > 0)
      .map(([key, label]) => `${label} ${(value[key] as number).toLocaleString("zh-CN")}`);
    return parts.length ? parts.join(" · ") : null;
  } catch {
    return null;
  }
}

function isTyping(target: EventTarget | null) {
  const element = target as HTMLElement | null;
  return !!element && (element.tagName === "INPUT" || element.tagName === "TEXTAREA" || element.tagName === "SELECT" || element.isContentEditable);
}

function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="mono inline-flex min-w-5 items-center justify-center rounded border border-line bg-ink px-1 text-[10px] leading-4 text-muted">{children}</kbd>;
}

function ConvertForm({ record, onCancel, onSubmit }: { record: EvidenceRecord; onCancel: () => void; onSubmit: (input: EvidenceReviewInput) => Promise<void> }) {
  const draft = useMemo(() => draftOpportunity(record), [record]);
  const [title, setTitle] = useState(draft.title);
  const [summary, setSummary] = useState(draft.summary);
  const [low, setLow] = useState("");
  const [high, setHigh] = useState("");
  const [busy, setBusy] = useState(false);
  const titleInput = useRef<HTMLInputElement>(null);
  useEffect(() => { titleInput.current?.select(); }, []);

  const min = parseBudget(low);
  const max = parseBudget(high);
  const budgetError = min === "invalid" || max === "invalid"
    ? "预算请填整数（元），不知道就留空"
    : (min === null) !== (max === null)
      ? "预算上下限要么都填，要么都空"
      : min !== null && max !== null && min > max ? "上限不能小于下限" : null;
  const ready = title.trim() && summary.trim() && !budgetError && !busy;

  async function submit() {
    if (!ready) return;
    setBusy(true);
    try { await onSubmit({ title: title.trim(), summary: summary.trim(), budget_min: min as number | null, budget_max: max as number | null }); }
    finally { setBusy(false); }
  }

  return (
    <form
      className="mt-4 space-y-3 rounded-lg border border-signal/30 bg-signal/[0.04] p-4"
      onSubmit={(event) => { event.preventDefault(); void submit(); }}
      onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); onCancel(); } }}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-mist">转为机会 <span className="ml-1 text-xs font-normal text-muted">已按原文预填，可直接修改</span></p>
        <button type="button" onClick={onCancel} className="text-muted hover:text-mist" aria-label="取消转换"><X size={16} /></button>
      </div>
      <input ref={titleInput} aria-label="机会标题" value={title} onChange={(event) => setTitle(event.target.value.slice(0, 200))} className="w-full rounded border border-line bg-ink px-3 py-2 text-sm text-mist outline-none focus:border-signal/60" />
      <textarea aria-label="机会摘要" value={summary} onChange={(event) => setSummary(event.target.value.slice(0, 2000))} rows={2} className="w-full resize-y rounded border border-line bg-ink px-3 py-2 text-sm text-mist outline-none focus:border-signal/60" />
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-xs text-muted">预算（元，可留空）</span>
        <input aria-label="预算下限" inputMode="numeric" value={low} onChange={(event) => setLow(event.target.value)} placeholder="下限" className="w-24 rounded border border-line bg-ink px-2 py-1.5 text-mist outline-none focus:border-signal/60" />
        <span className="text-muted">–</span>
        <input aria-label="预算上限" inputMode="numeric" value={high} onChange={(event) => setHigh(event.target.value)} placeholder="上限" className="w-24 rounded border border-line bg-ink px-2 py-1.5 text-mist outline-none focus:border-signal/60" />
        {budgetError && <span className="text-xs text-amber-200">{budgetError}</span>}
        <Button type="submit" disabled={!ready} className="ml-auto bg-signal/90 text-ink hover:bg-signal">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}确认转为机会 <Kbd>Enter</Kbd>
        </Button>
      </div>
    </form>
  );
}

function EvidenceRow({ record, selected, converting, onSelect, onReview, onStartConvert, onCancelConvert, onConvert }: {
  record: EvidenceRecord;
  selected: boolean;
  converting: boolean;
  onSelect: () => void;
  onReview: (input: EvidenceReviewInput) => Promise<void>;
  onStartConvert: () => void;
  onCancelConvert: () => void;
  onConvert: (input: EvidenceReviewInput) => Promise<void>;
}) {
  const status = statusOf(record);
  const grade = gradeOf(record);
  const engagement = engagementOf(record);
  const src = sourceOf(record);
  const author = authorOf(record);
  const savedNotes = String(record.notes ?? "");
  const [notes, setNotes] = useState(savedNotes);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [assessmentOpen,setAssessmentOpen] = useState(false);
  const [availability,setAvailability] = useState(record.assessment?.availability ?? "unknown");
  const [payment,setPayment] = useState(record.assessment?.payment ?? "unknown");
  const [eligibility,setEligibility] = useState(record.assessment?.eligibility ?? "needs_review");
  const [group,setGroup] = useState(String(record.metadata?.label_group ?? ""));
  useEffect(() => { setNotes(savedNotes); }, [savedNotes]);
  const long = record.raw_text.length > 280;
  const converted = typeof record.converted_opportunity_id === "string" && record.converted_opportunity_id;
  const urgency = typeof record.urgency_signal === "string" ? record.urgency_signal : null;
  const confidence = typeof record.classification_confidence === "number" ? Math.round(record.classification_confidence * 100) : null;
  const published = shortDate(record.published_at);

  return (
    <article
      id={`evidence-${record.evidence_id}`}
      onClick={onSelect}
      className={cn(
        "relative cursor-default rounded-lg border bg-panel/70 p-4 pl-5 transition",
        selected ? "border-ai/60 bg-panel shadow-glow" : "border-line hover:border-slate-500",
      )}
    >
      <span className={cn("absolute inset-y-3 left-0 w-0.5 rounded-full transition", selected ? "bg-ai" : "bg-transparent")} />
      <div className="flex gap-4">
        <div title={`证据等级 ${grade}`} className={cn("mono flex h-10 w-10 shrink-0 items-center justify-center rounded-md border text-lg font-semibold", GRADE_TONE[grade])}>{grade}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className={cn("rounded-full border px-2 py-0.5", STATUS_META[status].tone)}>{STATUS_META[status].label}</span>
            <span className="text-slate-300">{reasonLabel(record.classification_reason)}</span>
            {confidence !== null && <span className="mono text-muted">置信 {confidence}%</span>}
            <span className="ml-auto flex items-center gap-2 text-muted">
              <span className={cn("rounded-full border px-2 py-0.5 font-medium", src.tone)}>{src.label}</span>
              {author && <span className="max-w-32 truncate" title={`作者：${author}`}>@{author}</span>}
              <span className="mono">{published ? `发布 ${published}` : "发布时间未知"}</span>
              <a href={record.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="inline-flex items-center gap-1 text-indigo-200 hover:text-white">原文 <ExternalLink size={12} /></a>
              <button type="button" onClick={(event) => { event.stopPropagation(); void navigator.clipboard?.writeText(record.url).then(() => setCopied(true)); setTimeout(() => setCopied(false), 1500); }} className="text-muted hover:text-mist">{copied ? "已复制" : "复制链接"}</button>
            </span>
          </div>
          {record.metadata?.needs_review === "true" && <p className="mt-2 text-xs text-amber-200">存在分类冲突或原文更新，请重新核实；最新规则分类：{String(record.metadata.latest_predicted_category ?? record.category)}</p>}
          <p className="mt-2 text-xs text-muted">{evidenceBudgetLabel(record)} · 需求真实性：{status === "verified" ? "人工已核实" : "待人工核实"} · 采集 {shortDate(record.captured_at)}</p>
          {record.assessment && <div className="mt-2 text-xs text-muted"><p>需求状态：{{open:"有效",closed:"已关闭或过期",unknown:"未知"}[record.assessment.availability]} · 支付证据：{{explicit:"原文明确",unknown:"未知",no_budget:"明确无预算",conflicting:"冲突"}[record.assessment.payment]} · 服务适用性：{{eligible:"人工确认适用",excluded:"不适用",needs_review:"待核实"}[record.assessment.eligibility]}</p><p>{record.assessment.reason}</p>{[record.assessment.availability_quote,record.assessment.payment_quote,record.assessment.eligibility_quote].filter(Boolean).map((quote,i)=><p key={i} className="mt-1 text-amber-100">原文依据：{quote}</p>)}</div>}
          {Boolean(record.metadata?.local_fallback) && <p className="mt-2 text-xs text-muted">本地模型回退规则：{String(record.metadata?.local_fallback)}</p>}
          {Boolean(record.metadata?.local_category) && <p className="mt-2 text-xs text-muted">本地模型 {String(record.metadata?.local_mode)}：{String(record.metadata?.local_category)} · 置信度 {String(record.metadata?.local_confidence)}{record.metadata?.local_truncated === "true" ? " · 长文截断，需复核" : ""}</p>}
          <p className={cn("mt-2 whitespace-pre-line text-[15px] leading-7 text-slate-100", !selected ? "line-clamp-2" : !expanded && "line-clamp-6")}>{record.raw_text}</p>
          {selected && long && <button type="button" onClick={(event) => { event.stopPropagation(); setExpanded((value) => !value); }} className="mt-1 text-xs text-indigo-200 hover:text-white">{expanded ? "收起" : "展开全文"}</button>}
          {(record.payment_signal || urgency || engagement) && (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              {record.payment_signal && <span>付款信号 <b className="font-medium text-signal">{record.payment_signal}</b></span>}
              {urgency && <span>紧急 <b className="font-medium text-amber-200">{urgency}</b></span>}
              {engagement && <span>{engagement}</span>}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2" onClick={(event) => event.stopPropagation()}>
            {status !== "verified"
              ? <Button variant="secondary" className="min-h-8 px-2.5 text-xs" disabled={record.assessment?.actionable_candidate === false} onClick={() => void onReview({ verification_status: "verified" })}><Check size={13} />核实 {selected && <Kbd>V</Kbd>}</Button>
              : <Button variant="ghost" className="min-h-8 px-2.5 text-xs" onClick={() => void onReview({ verification_status: "unverified" })}><RotateCcw size={13} />退回待复核</Button>}
            {status !== "invalidated" && <Button variant="secondary" className="min-h-8 px-2.5 text-xs" onClick={() => void onReview({ verification_status: "invalidated" })}><X size={13} />排除 {selected && <Kbd>X</Kbd>}</Button>}
            {status === "invalidated" && <Button variant="ghost" className="min-h-8 px-2.5 text-xs" onClick={() => void onReview({ verification_status: "unverified" })}><RotateCcw size={13} />恢复</Button>}
            <select aria-label="修正分类" value={record.category} onChange={(event) => void onReview({ category: event.target.value as EvidenceCategory })} className="h-8 rounded border border-line bg-ink px-2 text-xs text-mist">
              {EVIDENCE_CATEGORIES.map((item, index) => <option key={item} value={item}>{index + 1} · {CATEGORY_LABELS[item]}</option>)}
            </select>
            <input
              aria-label="复核备注"
              value={notes}
              onChange={(event) => setNotes(event.target.value.slice(0, 2000))}
              onBlur={() => { if (notes !== savedNotes) void onReview({ notes }); }}
              onKeyDown={(event) => { if (event.key === "Enter") (event.target as HTMLInputElement).blur(); }}
              placeholder="备注（离开输入框自动保存）"
              className="h-8 min-w-40 flex-1 rounded border border-line bg-ink px-2 text-xs text-mist outline-none focus:border-ai"
            />
            {record.category === "buyer" && record.assessment?.actionable_candidate !== false && !converted && status !== "invalidated" && !converting && (
              <Button className="min-h-8 px-2.5 text-xs" onClick={onStartConvert}>
                <ArrowRight size={13} />{status === "verified" ? "转为机会" : "核实并转为机会"} {selected && <Kbd>C</Kbd>}
              </Button>
            )}
            {converted && <Link href={`/opportunities/${converted}`} className="inline-flex h-8 items-center gap-1 rounded border border-signal/40 px-2.5 text-xs text-signal hover:bg-signal/10">已转为机会 · 查看 <ArrowRight size={12} /></Link>}
          </div>
          <button className="mt-3 text-xs text-indigo-200" onClick={()=>setAssessmentOpen(x=>!x)}>纠正需求判断与标注分组</button>
          {assessmentOpen && <form className="mt-2 grid gap-2 text-xs sm:grid-cols-3" onClick={e=>e.stopPropagation()} onSubmit={e=>{e.preventDefault();void onReview({notes,assessment:{availability,payment,eligibility},...(group ? {label_group:group} : {})});}}>
            <label>有效状态<select aria-label="需求有效状态" className="mt-1 w-full rounded border border-line bg-ink p-2" value={availability} onChange={e=>setAvailability(e.target.value as typeof availability)}><option value="unknown">未知</option><option value="open">有效</option><option value="closed">已关闭</option></select></label>
            <label>支付证据<select aria-label="支付证据" className="mt-1 w-full rounded border border-line bg-ink p-2" value={payment} onChange={e=>setPayment(e.target.value as typeof payment)}><option value="unknown">未知</option><option value="explicit">原文明确</option><option value="no_budget">明确无预算</option><option value="conflicting">冲突</option></select></label>
            <label>服务适用性<select aria-label="服务适用性" className="mt-1 w-full rounded border border-line bg-ink p-2" value={eligibility} onChange={e=>setEligibility(e.target.value as typeof eligibility)}><option value="needs_review">待核实</option><option value="eligible">适用</option><option value="excluded">不适用</option></select></label>
            <label className="sm:col-span-2">同一原帖、转载或需求使用相同分组<input aria-label="标注分组" className="mt-1 w-full rounded border border-line bg-ink p-2" value={group} onChange={e=>setGroup(e.target.value.slice(0,150))}/></label><Button type="submit" disabled={!notes.trim()}>保存判断与依据</Button>
            <p className="sm:col-span-3 text-muted">先填写复核备注；原文明确关闭或不适用时不能通过纠正变为有效客户。</p>
          </form>}
          {converting && <ConvertForm record={record} onCancel={onCancelConvert} onSubmit={onConvert} />}
        </div>
      </div>
    </article>
  );
}

function EvidenceInbox() {
  const [records, setRecords] = useState<EvidenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<EvidenceCategory>("buyer");
  const [status, setStatus] = useState<StatusFilter>("pending");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortMode>("grade");
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [convertingId, setConvertingId] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [runtime, setRuntime] = useState<EvidenceRuntime | null>(null);
  const [metrics, setMetrics] = useState<AcquisitionMetrics | null>(null);
  const [billingRevision, setBillingRevision] = useState(0);
  const attemptRef = useRef<CollectionAttempt | null>(null);
  const [collectorOpen, setCollectorOpen] = useState(false);
  const [source, setSource] = useState<EvidenceSource>("rss");
  const [query, setQuery] = useState("");
  const [manualConfirmed, setManualConfirmed] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [nextPage, setNextPage] = useState<{source: EvidenceSource; query: string; cursor: string} | null>(null);
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
      if (!next.length) setCollectorOpen(true);
    } catch (reason) {
      setRecords([]);
      setMetrics(null);
      setError(reason instanceof Error ? reason.message : "加载证据失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Keep a selection inside the visible list so the keyboard always has a target.
  useEffect(() => {
    if (!visible.length) { if (selectedId !== null) setSelectedId(null); return; }
    if (!selected) setSelectedId(visible[0].evidence_id);
  }, [visible, selected, selectedId]);

  // Follow the selection only once the user starts moving it; the first auto-selection on load
  // must not scroll the header and filters out of view.
  const previousSelection = useRef<string | null>(null);
  useEffect(() => {
    if (selectedId && previousSelection.current !== null) document.getElementById(`evidence-${selectedId}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    previousSelection.current = selectedId;
  }, [selectedId]);

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
  }, [category, status, search, sort, sourceFilter, convertingId]);

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
  }, [applyRecord, showToast]);

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
  }, [visible, selected, selectedId, convertingId, review, startConvert]);

  async function collect(cursor?: string) {
    if (!query.trim()) { setCollectState("请先填写搜索词"); return; }
    setCollecting(true);
    setCollectState(null);
    try {
      const attempt = collectionAttempt(attemptRef.current,source,query,cursor,runtime?.billing_batch_id ?? undefined);
      attemptRef.current = attempt;
      const result = await collectEvidence(source, query.trim(), manualConfirmed, cursor, attempt.requestId,runtime?.billing_batch_id);
      attemptRef.current = null;
      setNextPage(result.next_cursor ? {source,query:query.trim(),cursor:result.next_cursor} : null);
      setManualConfirmed(false);
      setCollectState(`采集 ${result.fetched} 条，新增 ${result.inserted} 条，重复 ${result.duplicates} 条，过期 ${result.stale ?? 0} 条，拒绝 ${result.rejected} 条`);
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

  return (
    <>
      <PageHeader
        title="证据收件箱"
        description="先收集事实，再人工判断是否值得行动。处理过的证据会自动离开待复核队列。"
        action={<div className="flex gap-2">
          <Button variant="secondary" className="whitespace-nowrap" onClick={() => setCollectorOpen((value) => !value)}><Search size={15} /> 采集</Button>
          <Button variant="secondary" className="whitespace-nowrap" onClick={() => setImportOpen((value) => !value)}><Upload size={15} /> 导入</Button>
          <Button variant="secondary" onClick={()=>void exportEvidenceLabels().then(result=>{const href=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));const a=document.createElement("a");a.href=href;a.download="reviewed-labels.json";a.click();URL.revokeObjectURL(href);showToast({message:`已导出 ${result.count} 条人工标注，目标 ${result.target} 条`});}).catch(e=>showToast({message:e instanceof Error ? e.message : "导出失败"}))}>导出标注</Button>
          <Button variant="ghost" onClick={() => void load()} disabled={loading} aria-label="刷新"><RefreshCw size={15} className={loading ? "animate-spin" : ""} /></Button>
        </div>}
      />

      <BillingPanel refreshKey={billingRevision} />
      {metrics && <Panel className="mb-4 overflow-x-auto p-4"><h2 className="mb-2 font-semibold">来源获客漏斗</h2>{Object.keys(metrics.source_yield).length ? <table className="w-full text-left text-xs"><thead><tr className="text-muted"><th className="p-2">来源</th><th className="p-2">采集</th><th className="p-2">唯一证据</th><th className="p-2">买方候选</th><th className="p-2">人工核实买方</th></tr></thead><tbody>{Object.entries(metrics.source_yield).map(([name,row]) => <tr key={name} className="border-t border-line"><td className="p-2">{SOURCE_LABELS[name as EvidenceSource] ?? name}</td><td className="p-2">{row.collected}</td><td className="p-2">{row.evidence}</td><td className="p-2">{row.buyer}</td><td className="p-2">{row.verified_buyer}</td></tr>)}</tbody></table> : <p className="text-sm text-muted">暂无数据</p>}<p className="mt-2 text-xs text-muted">买方候选是分类判断，人工核实由你查看公开原文后记录。</p></Panel>}
      {runtime?.warning && <p className="mb-4 rounded-md border border-amber-400/20 bg-amber-400/[0.06] px-3 py-2 text-xs text-amber-100">{runtime.warning}</p>}

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
          <Button type="submit" disabled={collecting || !runtime?.sources[source]?.configured || !!paidBlocked}>{collecting && <Loader2 size={15} className="animate-spin" />}{collecting ? "采集中…" : "开始采集"}</Button>
        </form>
        {source === "rss" && <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">免费预设：{FEED_PRESETS.map((preset) => <button key={preset.url} type="button" onClick={() => setQuery(preset.url)} className={cn("rounded border px-2 py-0.5 transition", query === preset.url ? "border-ai/60 text-indigo-100" : "border-line hover:text-mist")}>{preset.label}</button>)}</div>}
        {["个人文档","企业视频与开发"].map(group => <div key={group} className="mt-2 flex flex-wrap gap-2 text-xs text-muted"><span>{group}：</span>{KEYWORD_PRESETS.filter(x => x.group === group).map(preset => <button type="button" key={preset.query} className="rounded border border-line px-2 py-1 hover:text-mist" onClick={() => {setSource(preset.source);setQuery(preset.query);setManualConfirmed(false);}}>{preset.query}</button>)}</div>)}
        {billable && <p className="mt-2 text-xs text-amber-100">{requestPrice ? `此接口已核实单价 $${requestPrice.toFixed(4)} / 次；单击仅取一页。` : "接口价格未核实，付费采集被阻止。"}</p>}
        {runtime?.sources[source]?.validation_status && <p className="mt-2 text-xs text-muted">来源验证：{({contract_only:"离线契约通过；尚未实采验证",response_compatible:"已存真实响应可解析；分页与业务效果仍需核实",response_incompatible:"已存响应解析不兼容"} as Record<string,string>)[runtime.sources[source].validation_status ?? ""] ?? runtime.sources[source].validation_status}</p>}
        {runtime?.sources[source]?.pricing_evidence && <p className="mt-1 text-xs text-muted">价格依据：<a href={runtime.sources[source].pricing_evidence?.source_url} target="_blank" rel="noreferrer" className="underline">官方来源</a> · 核实 {shortDate(runtime.sources[source].pricing_evidence?.verified_at)}</p>}
        {billable && <label className="mt-2 flex items-center gap-2 text-xs text-amber-100"><input type="checkbox" checked={manualConfirmed} onChange={(event) => setManualConfirmed(event.target.checked)} />该来源按调用收费，我确认本次采集</label>}
        {nextPage && nextPage.source === source && nextPage.query === query.trim() && <Button className="mt-3" variant="secondary" disabled={collecting || !!paidBlocked} onClick={() => void collect(nextPage.cursor)}>采集下一页（独立请求）</Button>}
        {collectState && <p className="mt-2 text-sm text-muted">{collectState}</p>}
        {collectState && attemptRef.current && <Button className="mt-2" variant="secondary" onClick={() => {attemptRef.current=null;setManualConfirmed(false);setCollectState("已准备新的请求；如需付费，请重新确认，新的调用会占用额度。");}}>准备新的采集请求</Button>}
      </Panel>}

      {importOpen && <Panel className="mb-4 p-4">
        <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2"><FileJson size={16} className="text-indigo-300" /><p className="text-sm font-medium text-mist">导入证据 JSON <span className="ml-1 text-xs font-normal text-muted">支持证据数组，导入后去重，原文不改写</span></p></div><button className="text-muted hover:text-mist" onClick={() => setImportOpen(false)} aria-label="关闭导入"><ChevronDown size={18} /></button></div>
        <textarea value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='[{"source":"tikhub","url":"https://...","raw_text":"...","category":"market"}]' className="mt-3 min-h-28 w-full rounded-lg border border-line bg-ink p-3 font-mono text-xs text-slate-200 outline-none focus:border-ai" aria-label="Evidence JSON" />
        <div className="mt-2 flex flex-wrap items-center gap-3"><input ref={fileInput} type="file" accept="application/json,.json" className="hidden" onChange={(event) => { const file = event.target.files?.[0]; if (file) void readFile(file); }} /><Button variant="secondary" onClick={() => fileInput.current?.click()} disabled={importing}><Upload size={15} /> 读取文件</Button><Button onClick={() => void importEvidence()} disabled={!importText.trim() || importing}>{importing && <Loader2 size={15} className="animate-spin" />}{importing ? "导入中…" : "提交导入"}</Button>{importState && <span className="text-sm text-muted">{importState}</span>}</div>
      </Panel>}

      <div role="tablist" aria-label="证据分类" className="mb-4 grid gap-2 sm:grid-cols-3">
        {EVIDENCE_CATEGORIES.map((item, index) => {
          const active = category === item;
          const count = counts[item];
          return (
            <button key={item} role="tab" aria-selected={active} onClick={() => { setCategory(item); setSourceFilter(null); }} className={cn("rounded-lg border p-3 text-left transition", active ? "border-ai/60 bg-ai/10" : "border-line bg-panel/50 hover:border-slate-500")}>
              <div className="flex items-baseline justify-between gap-2">
                <p className={cn("text-sm font-medium", active ? "text-indigo-100" : "text-mist")}>{CATEGORY_LABELS[item]}</p>
                <p className="mono text-xs text-muted"><b className={cn("text-base font-semibold", count.pending ? "text-amber-200" : "text-muted")}>{count.pending}</b> 待复核 · 共 {count.all}</p>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted">{descriptions[item]}</p>
              <span className="sr-only">分类快捷键 {index + 1}</span>
            </button>
          );
        })}
      </div>

      <div className="sticky top-0 z-10 -mx-1 mb-3 flex flex-wrap items-center gap-2 bg-ink/90 px-1 py-2 backdrop-blur">
        <div className="flex rounded-md border border-line bg-panel/60 p-0.5" role="group" aria-label="复核状态">
          {STATUS_FILTERS.map((item) => (
            <button key={item.value} onClick={() => setStatus(item.value)} aria-pressed={status === item.value} className={cn("rounded px-2.5 py-1 text-xs transition", status === item.value ? "bg-ai/20 text-indigo-100" : "text-muted hover:text-mist")}>
              {item.label} <span className="mono opacity-70">{counts[category][item.value]}</span>
            </button>
          ))}
        </div>
        <label className="relative min-w-48 flex-1">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input ref={searchInput} value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Escape") { setSearch(""); event.currentTarget.blur(); } }} placeholder="在当前分类里搜索原文或备注" aria-label="搜索证据" className="h-8 w-full rounded-md border border-line bg-panel/60 pl-8 pr-8 text-xs text-mist outline-none focus:border-ai" />
          <span className="absolute right-2 top-1/2 -translate-y-1/2"><Kbd>/</Kbd></span>
        </label>
        <select value={sort} onChange={(event) => setSort(event.target.value as SortMode)} aria-label="排序" className="h-8 rounded-md border border-line bg-panel/60 px-2 text-xs text-mist">
          <option value="grade">等级优先</option>
          <option value="latest">最新优先</option>
        </select>
      </div>
      {sources.length > 0 && <div className="mb-3 flex flex-wrap items-center gap-1.5 text-xs" role="group" aria-label="按来源筛选">
        <span className="text-muted">来源</span>
        <button onClick={() => setSourceFilter(null)} aria-pressed={sourceFilter === null} className={cn("rounded-full border px-2.5 py-0.5 transition", sourceFilter === null ? "border-ai/60 bg-ai/20 text-indigo-100" : "border-line text-muted hover:text-mist")}>全部</button>
        {sources.map((item) => <button key={item.key} onClick={() => setSourceFilter(sourceFilter === item.key ? null : item.key)} aria-pressed={sourceFilter === item.key} className={cn("rounded-full border px-2.5 py-0.5 transition", sourceFilter === item.key ? item.tone : "border-line text-muted hover:text-mist")}>{item.label} <span className="mono opacity-70">{item.count}</span></button>)}
      </div>}
      <p className="mb-3 hidden flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted sm:flex">
        <span><Kbd>J</Kbd> <Kbd>K</Kbd> 上下</span><span><Kbd>V</Kbd> 核实</span><span><Kbd>X</Kbd> 排除</span><span><Kbd>U</Kbd> 退回</span><span><Kbd>C</Kbd> 转为机会</span><span><Kbd>O</Kbd> 原文</span><span><Kbd>1</Kbd>–<Kbd>5</Kbd> 改分类</span>
      </p>

      {loading && <Panel className="flex items-center justify-center gap-2 p-10 text-sm text-muted"><Loader2 className="animate-spin" size={18} /> 正在加载证据…</Panel>}
      {!loading && error && <Panel className="border-red-400/30 p-6"><div className="flex items-start gap-3 text-red-200"><AlertCircle size={19} className="mt-0.5 shrink-0" /><div><p className="font-medium">加载失败</p><p className="mt-1 text-sm text-red-200/80">{error}</p><Button className="mt-4" variant="secondary" onClick={() => void load()}>重试</Button></div></div></Panel>}
      {!loading && !error && visible.length === 0 && (
        counts[category].all > 0 && status === "pending" && !search
          ? <EmptyState title={`「${CATEGORY_LABELS[category]}」已全部复核完 🎉`}><p className="text-sm text-muted">核实 {counts[category].verified} 条，排除 {counts[category].invalidated} 条。</p><Button className="mt-4" variant="secondary" onClick={() => setStatus("verified")}>查看已核实</Button></EmptyState>
          : <EmptyState title={search ? `没有匹配「${search}」的证据` : `还没有${CATEGORY_LABELS[category]}`}>{!search && <><p className="text-sm text-muted">可以先采集一次，或者导入一批真实来源数据。</p><Button className="mt-4" onClick={() => setCollectorOpen(true)}>开始采集</Button></>}</EmptyState>
      )}
      {!loading && !error && visible.length > 0 && (
        <div className="space-y-2 pb-24">
          {visible.map((record) => (
            <EvidenceRow
              key={record.evidence_id}
              record={record}
              selected={record.evidence_id === selectedId}
              converting={record.evidence_id === convertingId}
              onSelect={() => setSelectedId(record.evidence_id)}
              onReview={(input) => review(record, input)}
              onStartConvert={() => void startConvert(record)}
              onCancelConvert={() => { setConvertingId(null); const left = recordsRef.current.find((item) => item.evidence_id === record.evidence_id); if (left) applyRecord(left, record.evidence_id, null); }}
              onConvert={(input) => convert(record, input)}
            />
          ))}
        </div>
      )}

      {toast && (
        <div role="status" onMouseEnter={holdToast} onMouseLeave={releaseToast} className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-3 rounded-lg border border-line bg-panel px-4 py-2.5 text-sm text-mist shadow-xl">
          <span className="max-w-[60vw] truncate">{toast.message}</span>
          {toast.href && <Link href={toast.href} className="text-signal hover:underline">查看</Link>}
          {toast.undo && <button className="font-medium text-indigo-200 hover:text-white" onClick={() => { const undo = toast.undo; showToast(null); void undo?.(); }}>撤销</button>}
        </div>
      )}
    </>
  );
}

export default function Page() { return <AppShell><EvidenceInbox /></AppShell>; }
