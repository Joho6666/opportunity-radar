"use client";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowRight, Check, ExternalLink, Loader2, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { EVIDENCE_CATEGORIES, type EvidenceCategory, type EvidenceRecord, type EvidenceReviewInput } from "@/lib/evidence-client";
import { CATEGORY_LABELS, STATUS_META, authorOf, draftOpportunity, evidenceBudgetLabel, gradeOf, parseBudget, reasonLabel, sourceOf, statusOf } from "@/lib/evidence-view";
const GRADE_TONE = { A:"border-signal/40 bg-emerald-50 text-signal",B:"border-indigo-200 bg-indigo-50 text-ai",C:"border-line bg-ink text-muted" };
export function shortDate(value: string | null | undefined) {
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

function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="mono inline-flex min-w-5 items-center justify-center rounded border border-line bg-ink px-1 text-xs leading-4 text-muted">{children}</kbd>;
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
        {budgetError && <span className="text-xs text-amber-800">{budgetError}</span>}
        <Button type="submit" disabled={!ready} className="ml-auto bg-signal/90 text-ink hover:bg-signal">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <ArrowRight size={14} />}确认转为机会 <Kbd>Enter</Kbd>
        </Button>
      </div>
    </form>
  );
}

export function EvidenceDetail({ record, selected, converting, notesDraft, onNotesDraft, onSelect, onReview, onStartConvert, onCancelConvert, onConvert }: {
  record: EvidenceRecord;
  selected: boolean;
  notesDraft?: string;
  onNotesDraft?: (value:string)=>void;
  converting: boolean;
  onSelect: () => void;
  onReview: (input: EvidenceReviewInput) => Promise<boolean>;
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
  const [notes, setNotes] = useState(notesDraft ?? savedNotes);
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [assessmentOpen,setAssessmentOpen] = useState(false);
  const [availability,setAvailability] = useState(record.assessment?.availability ?? "unknown");
  const [payment,setPayment] = useState(record.assessment?.payment ?? "unknown");
  const [eligibility,setEligibility] = useState(record.assessment?.eligibility ?? "needs_review");
  const [group,setGroup] = useState(String(record.metadata?.label_group ?? ""));
  useEffect(() => { if(notesDraft === undefined)setNotes(savedNotes); }, [savedNotes,notesDraft]);
  const long = record.raw_text.length > 280;
  const converted = typeof record.converted_opportunity_id === "string" && record.converted_opportunity_id;
  const urgency = typeof record.urgency_signal === "string" ? record.urgency_signal : null;
  const confidence = record.classification_source === "unclassified" ? null : typeof record.classification_confidence === "number" ? Math.round(record.classification_confidence * 100) : null;
  const published = shortDate(record.ranking ? record.ranking.signals.published_at : record.published_at);

  return (
    <article
      data-evidence-detail={record.evidence_id}
      onClick={onSelect}
      className={cn(
        "relative min-w-0 bg-white p-4",
        
      )}
    >
      <span className={cn("absolute inset-y-3 left-0 w-0.5 rounded-full transition", selected ? "bg-ai" : "bg-transparent")} />
      <div>
        <div title={`证据等级 ${grade}`} className={cn("mono mb-3 inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold", GRADE_TONE[grade])}>证据等级 {grade}</div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            <span className={cn("rounded-full border px-2 py-0.5", STATUS_META[status].tone)}>{STATUS_META[status].label}</span>
            <span className="text-slate-600">{reasonLabel(record.classification_reason)}</span>
            {confidence !== null && <span className="mono text-muted">置信 {confidence}%</span>}
            <span className="flex flex-wrap items-center gap-2 text-muted">
              <span className={cn("rounded-full border px-2 py-0.5 font-medium", src.tone)}>{src.label}</span>
              {author && <span className="max-w-32 truncate" title={`作者：${author}`}>@{author}</span>}
              <span className="mono">{published ? `发布 ${published}` : "发布时间未知"}</span>
              <a href={record.url} target="_blank" rel="noreferrer" onClick={(event) => event.stopPropagation()} className="inline-flex items-center gap-1 text-indigo-700 hover:text-mist">原文 <ExternalLink size={12} /></a>
              <button type="button" onClick={(event) => { event.stopPropagation(); void navigator.clipboard?.writeText(record.url).then(() => setCopied(true)); setTimeout(() => setCopied(false), 1500); }} className="text-muted hover:text-mist">{copied ? "已复制" : "复制链接"}</button>
            </span>
          </div>
          {record.metadata?.needs_review === "true" && <p className="mt-2 text-xs text-amber-800">存在分类冲突或原文更新，请重新核实；最新规则分类：{String(record.metadata.latest_predicted_category ?? record.category)}</p>}
          <p className="mt-2 text-xs text-muted">{evidenceBudgetLabel(record)} · 需求真实性：{status === "verified" ? "人工已核实" : "待人工核实"} · 采集 {shortDate(record.captured_at)}</p>
          {record.ranking && <div className="mt-2 rounded border border-line p-2 text-xs text-muted">
            <p><span className="font-medium text-mist">获客优先级 {record.ranking.lead_score}/100</span> · 热度 {record.ranking.signals.heat_score === null ? "未知" : `${record.ranking.signals.heat_score}/100`} · {record.ranking.signals.author_visible ? "公开作者可见" : "作者未知"} · 真人身份待核实</p>
            <p className="mt-1">{record.ranking.label}</p>
            {selected && <details className="mt-1"><summary className="cursor-pointer text-indigo-700">评分依据与活跃信号</summary><ul className="mt-2 list-inside list-disc space-y-1">{record.ranking.reasons.map((reason,index)=><li key={index}>{reason}</li>)}</ul><p className="mt-2">{record.ranking.signals.heat_reason}</p><p>来源最近活动：{shortDate(record.ranking.signals.last_activity_at) ?? "未知"} · 累计评论：{record.ranking.signals.comments ?? "未知"}（评论发生时间未知）</p></details>}
          </div>}
          {record.assessment && <div className="mt-2 text-xs text-muted"><p>需求状态：{{open:"有效",closed:"已关闭或过期",unknown:"未知"}[record.assessment.availability]} · 支付证据：{{explicit:"原文明确",unknown:"未知",no_budget:"明确无预算",conflicting:"冲突"}[record.assessment.payment]} · 服务适用性：{{eligible:"人工确认适用",excluded:"不适用",needs_review:"待核实"}[record.assessment.eligibility]}</p><p>{record.assessment.reason}</p>{[record.assessment.availability_quote,record.assessment.payment_quote,record.assessment.eligibility_quote].filter(Boolean).map((quote,i)=><p key={i} className="mt-1 text-amber-900">原文依据：{quote}</p>)}</div>}
          {Boolean(record.metadata?.local_fallback) && <p className="mt-2 text-xs text-muted">本地模型回退规则：{String(record.metadata?.local_fallback)}</p>}
          {Boolean(record.metadata?.local_category) && <p className="mt-2 text-xs text-muted">本地模型 {String(record.metadata?.local_mode)}：{String(record.metadata?.local_category)} · 置信度 {String(record.metadata?.local_confidence)}{record.metadata?.local_truncated === "true" ? " · 长文截断，需复核" : ""}</p>}
          <p className={cn("mt-2 whitespace-pre-line text-[15px] leading-7 text-slate-900", !selected ? "line-clamp-2" : !expanded && "line-clamp-6")}>{record.raw_text}</p>
          {selected && long && <button type="button" onClick={(event) => { event.stopPropagation(); setExpanded((value) => !value); }} className="mt-1 text-xs text-indigo-700 hover:text-mist">{expanded ? "收起" : "展开全文"}</button>}
          {(record.payment_signal || urgency || engagement) && (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              {record.payment_signal && <span>付款信号 <b className="font-medium text-signal">{record.payment_signal}</b></span>}
              {urgency && <span>紧急 <b className="font-medium text-amber-800">{urgency}</b></span>}
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
              onChange={(event) => {const value=event.target.value.slice(0,2000);setNotes(value);onNotesDraft?.(value);}}
              onBlur={() => { if (notes !== savedNotes) void onReview({ notes }); }}
              onKeyDown={(event) => { if (event.key === "Enter") (event.target as HTMLInputElement).blur(); }}
              placeholder="备注（离开输入框自动保存）"
              className="h-8 min-w-40 flex-1 rounded border border-line bg-ink px-2 text-xs text-mist outline-none focus:border-ai"
            />
            {notes!==savedNotes&&<Button variant="secondary" onClick={()=>void onReview({notes})}>重试保存备注</Button>}
            {record.category === "buyer" && record.assessment?.actionable_candidate !== false && !converted && status !== "invalidated" && !converting && (
              <Button className="min-h-8 px-2.5 text-xs" onClick={onStartConvert}>
                <ArrowRight size={13} />{status === "verified" ? "转为机会" : "核实并转为机会"} {selected && <Kbd>C</Kbd>}
              </Button>
            )}
            {converted && <Link href={`/opportunities/${converted}`} className="inline-flex h-8 items-center gap-1 rounded border border-signal/40 px-2.5 text-xs text-signal hover:bg-signal/10">已转为机会 · 查看 <ArrowRight size={12} /></Link>}
          </div>
          <button className="mt-3 text-xs text-indigo-700" onClick={()=>setAssessmentOpen(x=>!x)}>纠正需求判断与标注分组</button>
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

