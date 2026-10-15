import type { EvidenceCategory, EvidenceRecord } from "@/lib/evidence-client";

export type ReviewStatus = "unverified" | "verified" | "invalidated" | "disputed";
export type StatusFilter = "pending" | "verified" | "invalidated" | "all";
export type SortMode = "grade" | "latest" | "hot" | "lead";

export const CATEGORY_LABELS: Record<EvidenceCategory, string> = {
  buyer: "潜在购买需求",
  seller: "服务商广告",
  job: "招聘与求职",
  content: "内容问题",
  market: "市场变化",
};

export const STATUS_FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "pending", label: "待复核" },
  { value: "verified", label: "已核实" },
  { value: "invalidated", label: "已排除" },
  { value: "all", label: "全部" },
];

const REASONS: Record<string, string> = {
  explicit_request_budget_deadline: "公开求助或项目需求，预算与时限需看原文",
  audience_question_or_howto: "受众提问或求教程",
  content_or_trend_without_buying_intent: "内容或趋势，无购买意图",
  seller_self_promotion: "卖方自荐，不是买方",
  advice_or_listicle: "经验文或清单文，不是需求",
  implicit_project_request: "合作或交付需求，需核实项目关系及预算",
};

export function reasonLabel(code: string | undefined): string {
  if (!code) return "未记录";
  return REASONS[code] ?? code;
}

export const STATUS_META: Record<ReviewStatus, { label: string; tone: string }> = {
  unverified: { label: "待复核", tone: "border-amber-400/30 bg-amber-400/10 text-amber-800" },
  verified: { label: "已核实", tone: "border-emerald-400/30 bg-emerald-400/10 text-emerald-800" },
  invalidated: { label: "已排除", tone: "border-rose-400/30 bg-rose-400/10 text-rose-700" },
  disputed: { label: "有争议", tone: "border-sky-400/30 bg-sky-400/10 text-sky-800" },
};

export function statusOf(record: EvidenceRecord): ReviewStatus {
  const value = record.verification_status as ReviewStatus;
  return value in STATUS_META ? value : "unverified";
}

export function gradeOf(record: EvidenceRecord): "A" | "B" | "C" {
  const value = String(record.evidence_grade ?? "C").toUpperCase();
  return value === "A" || value === "B" ? value : "C";
}

function matchesStatus(record: EvidenceRecord, filter: StatusFilter): boolean {
  const status = statusOf(record);
  if (filter === "all") return true;
  if (record.category === "buyer" && record.assessment?.actionable_candidate === false && filter !== "invalidated") return false;
  if (filter === "pending") return status === "unverified" || status === "disputed";
  return status === filter;
}

function matchesSearch(record: EvidenceRecord, search: string): boolean {
  const keyword = search.trim().toLowerCase();
  if (!keyword) return true;
  return `${record.raw_text} ${record.notes ?? ""} ${record.source_platform ?? ""} ${record.query ?? ""}`.toLowerCase().includes(keyword);
}

/** `keep` pins one record (the one being converted) so a status change does not pull it out of view. */
const PLATFORM_NAMES: Record<string, { label: string; tone: string }> = {
  douyin: { label: "抖音", tone: "border-rose-400/40 bg-rose-400/10 text-rose-700" },
  xiaohongshu: { label: "小红书", tone: "border-red-400/40 bg-red-400/10 text-red-700" },
  weibo: { label: "微博", tone: "border-orange-400/40 bg-orange-400/10 text-orange-800" },
  zhihu: { label: "知乎", tone: "border-sky-400/40 bg-sky-400/10 text-sky-800" },
  tiktok: { label: "TikTok", tone: "border-fuchsia-400/40 bg-fuchsia-400/10 text-fuchsia-800" },
  hackernews: { label: "Hacker News", tone: "border-amber-400/40 bg-amber-400/10 text-amber-800" },
  github: { label: "GitHub", tone: "border-slate-400/40 bg-slate-400/10 text-slate-800" },
  "v2ex.com": { label: "V2EX", tone: "border-emerald-400/40 bg-emerald-400/10 text-emerald-800" },
};

/** Where a post came from, by name. An RSS item is named after its site, not "rss". */
export function sourceOf(record: EvidenceRecord): { key: string; label: string; tone: string } {
  let key = String(record.source_platform || record.source || "unknown");
  if (key === "rss") {
    try { key = new URL(record.url).hostname.replace(/^www\./, ""); } catch { key = "rss"; }
  }
  const known = PLATFORM_NAMES[key];
  return { key, label: known?.label ?? (key === "rss" ? "RSS" : key), tone: known?.tone ?? "border-line bg-ink/60 text-slate-600" };
}

export function authorOf(record: EvidenceRecord): string | null {
  const value = record.metadata?.raw_author;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Sources present in a category, most frequent first, for the filter chips. */
export function sourcesIn(records: EvidenceRecord[], category: EvidenceCategory): { key: string; label: string; tone: string; count: number }[] {
  const map = new Map<string, { key: string; label: string; tone: string; count: number }>();
  for (const record of records) {
    if (record.category !== category) continue;
    const source = sourceOf(record);
    map.set(source.key, { ...source, count: (map.get(source.key)?.count ?? 0) + 1 });
  }
  return [...map.values()].sort((a, b) => b.count - a.count);
}

export function visibleRecords(records: EvidenceRecord[], options: { category: EvidenceCategory; status: StatusFilter; search: string; sort: SortMode; keep?: string | null; source?: string | null }): EvidenceRecord[] {
  const rank = { A: 0, B: 1, C: 2 };
  const time = (record: EvidenceRecord) => new Date((record.ranking ? record.ranking.signals.published_at : record.published_at) ?? "").getTime() || 0;
  const score = (record: EvidenceRecord) => options.sort === "hot" ? record.ranking?.signals.heat_score ?? -1 : record.ranking?.lead_score ?? -1;
  return records
    .filter((record) => record.category === options.category && (record.evidence_id === options.keep || (matchesStatus(record, options.status) && matchesSearch(record, options.search) && (!options.source || sourceOf(record).key === options.source))))
    .sort((a, b) => options.sort === "hot" || options.sort === "lead"
      ? score(b) - score(a) || time(b) - time(a)
      : options.sort === "latest"
      ? time(b) - time(a)
      : rank[gradeOf(a)] - rank[gradeOf(b)] || (b.classification_confidence ?? 0) - (a.classification_confidence ?? 0) || time(b) - time(a));
}

export function countBy(records: EvidenceRecord[], category: EvidenceCategory): Record<StatusFilter, number> {
  const inCategory = records.filter((record) => record.category === category);
  return {
    pending: inCategory.filter((record) => matchesStatus(record, "pending")).length,
    verified: inCategory.filter((record) => matchesStatus(record, "verified")).length,
    invalidated: inCategory.filter((record) => matchesStatus(record, "invalidated")).length,
    all: inCategory.length,
  };
}

/** A starting point for the conversion form, taken from the evidence's own words. */
export function draftOpportunity(record: EvidenceRecord): { title: string; summary: string } {
  const text = record.raw_text.replace(/\s+/g, " ").trim();
  const firstClause = text.split(/[，。！？,.!?；;]/)[0]?.trim() || text;
  const title = firstClause.length > 28 ? `${firstClause.slice(0, 28)}…` : firstClause;
  return { title, summary: text.slice(0, 300) };
}

/** Parses an optional budget field: blank means unknown, anything else must be a non-negative integer. */
export function parseBudget(value: string): number | null | "invalid" {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const number = Number(trimmed);
  return Number.isInteger(number) && number >= 0 ? number : "invalid";
}

export function evidenceBudgetLabel(record: EvidenceRecord): string {
  try {
    const facts = JSON.parse(String(record.metadata?.facts ?? "{}")) as {budget_min?:number|null;budget_max?:number|null;budget_bound?:string;currency?:string|null};
    const manual = record.metadata?.budget_min !== undefined || record.metadata?.budget_max !== undefined;
    const low = manual ? parseBudget(String(record.metadata?.budget_min ?? "")) : facts.budget_min;
    const high = manual ? parseBudget(String(record.metadata?.budget_max ?? "")) : facts.budget_max;
    const values = [low,high].filter((value):value is number => typeof value === "number" && Number.isFinite(value) && value>=0);
    if (!values.length) return "预算未知";
    const range = !manual && facts.budget_bound === "lower" ? `${values[0]}+` : values.length===2 && values[0]!==values[1] ? `${values[0]}–${values[1]}` : String(values[0]);
    return `${manual ? "人工记录预算" : "预算"} ${facts.currency || "币种未知"} ${range}`;
  } catch { return "预算未知"; }
}
