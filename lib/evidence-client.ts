import { getAccessToken } from "@/lib/auth";
import type { CollectionPolicy } from "@/lib/collection-policy";

export type PostRanking = {kind:"prediction";lead_score:number;label:string;reasons:string[];signals:{published_at:string|null;last_activity_at:string|null;age_hours:number|null;author_visible:boolean;identity_status:"unverified";comments:number|null;interactions:number|null;heat_score:number|null;heat_reason:string}};

export const EVIDENCE_CATEGORIES = ["buyer", "seller", "job", "content", "market"] as const;
export type EvidenceCategory = (typeof EVIDENCE_CATEGORIES)[number];
export type DemandAssessment = {
  availability: "open" | "closed" | "unknown";
  payment: "explicit" | "unknown" | "no_budget" | "conflicting";
  eligibility: "eligible" | "excluded" | "needs_review";
  availability_quote?: string | null; payment_quote?: string | null; eligibility_quote?: string | null;
  reason?: string; actionable_candidate: boolean;
};

export type EvidenceRecord = {
  evidence_id: string;
  source: string;
  url: string;
  raw_text: string;
  published_at: string | null;
  captured_at: string;
  category: EvidenceCategory;
  payment_signal: string | null;
  verification_status: string;
  classification_source?: string;
  classification_reason?: string;
  classification_confidence?: number;
  source_platform?: string;
  acquisition_tool?: string;
  metadata?: Record<string, unknown>;
  assessment?: DemandAssessment;
  ranking?: PostRanking;
  [key: string]: unknown;
};

export type EvidenceInput = {
  source: string;
  url: string;
  raw_text: string;
  query?: string;
  external_id?: string | null;
  published_at?: string | null;
  captured_at?: string | null;
  category: EvidenceCategory;
  buyer_type?: string | null;
  problem?: string | null;
  payment_signal?: string | null;
  urgency_signal?: string | null;
  metadata?: Record<string, string>;
};

export type EvidenceBatchResult = {
  batch_id: string | null;
  inserted: number;
  duplicates: number;
  records: EvidenceRecord[];
};

export const EVIDENCE_SOURCES = ["rss", "douyin", "xiaohongshu", "weibo", "zhihu", "tikhub", "hackernews", "github", "web_search"] as const;
export type EvidenceSource = (typeof EVIDENCE_SOURCES)[number];
export const SOURCE_LABELS: Record<EvidenceSource, string> = {
  rss: "RSS（含 V2EX）",
  douyin: "抖音",
  xiaohongshu: "小红书",
  weibo: "微博",
  zhihu: "知乎",
  tikhub: "TikTok",
  hackernews: "Hacker News",
  github: "GitHub",
  web_search: "网页搜索",
};
/** Sources billed per call (TikHub, Firecrawl); the API refuses them without manual confirmation. */
export const BILLABLE_SOURCES: ReadonlySet<EvidenceSource> = new Set(["douyin", "xiaohongshu", "weibo", "zhihu", "tikhub", "web_search"]);
/** Free domestic feeds worth polling for paid work. */
export const FEED_PRESETS = [
  { label: "V2EX 外包", url: "https://www.v2ex.com/feed/outsourcing.xml" },
  { label: "V2EX 酷工作", url: "https://www.v2ex.com/feed/jobs.xml" },
  { label: "V2EX 远程", url: "https://www.v2ex.com/feed/remote.xml" },
] as const;
export const KEYWORD_PRESETS: { group: string; source: EvidenceSource; query: string }[] = [
  {group:"个人文档",source:"xiaohongshu",query:"找人做PPT"},
  {group:"个人文档",source:"weibo",query:"求助 Word排版"},
  {group:"个人文档",source:"xiaohongshu",query:"找人修改简历"},
  {group:"个人文档",source:"xiaohongshu",query:"论文格式检查"},
  {group:"企业视频与开发",source:"douyin",query:"找人剪视频"},
  {group:"企业视频与开发",source:"xiaohongshu",query:"找人制作商品宣传片"},
  {group:"企业视频与开发",source:"xiaohongshu",query:"找人开发小程序"},
  {group:"企业视频与开发",source:"weibo",query:"找人做网站"},
];
export type CollectionAttempt = { fingerprint: string; requestId: string };
export function collectionAttempt(previous: CollectionAttempt | null, source: EvidenceSource, query: string, cursor?: string, batchId?: string, configKey?: string): CollectionAttempt {
  const fingerprint = JSON.stringify([source,query.trim(),cursor ?? null,batchId ?? null,configKey ?? null]);
  return previous?.fingerprint === fingerprint ? previous : {fingerprint,requestId:crypto.randomUUID()};
}
export type SourceYield = {collected:number;evidence:number;buyer:number;verified_buyer:number;buyer_ratio:number|null};
export type AcquisitionMetrics = {source_yield:Record<string,SourceYield>};
export type EvidenceRuntime = {
  paid_api_enabled?: boolean;
  billing_batch_id?: string | null;
  billing_batch?: {remaining_requests:number;remaining_cost_usd:number;enabled:boolean} | null;
  storage_mode: "memory" | "postgres";
  warning: string | null;
  sources: Record<EvidenceSource, { configured: boolean; estimated_request_cost_usd?: number | null; validation_status?: string; live_verified?: boolean; pricing_evidence?: {source_url:string;verified_at:string;unit:string} | null }>;
};
export type EvidenceCollectResult = EvidenceBatchResult & { next_cursor?: string | null; billing_batch_id?:string|null;request_id?:string|null; fetched: number; rejected: number; stale?:number; filtered?:{stale:number;unknown_date:number;terms:number;activity:number}; warning: string | null };

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8011";

export function buildEvidenceQuery(category: EvidenceCategory, limit = 100): string {
  const params = new URLSearchParams({ category, limit: String(limit) });
  return `/api/intelligence/evidence?${params.toString()}`;
}

function isCategory(value: unknown): value is EvidenceCategory {
  return typeof value === "string" && EVIDENCE_CATEGORIES.includes(value as EvidenceCategory);
}

function validateInput(value: unknown, index: number): EvidenceInput {
  if (!value || typeof value !== "object") throw new Error(`Evidence item ${index + 1} must be an object`);
  const item = value as Record<string, unknown>;
  for (const key of ["raw_text", "source", "url"]) {
    if (typeof item[key] !== "string" || !item[key]) throw new Error(`Evidence item ${index + 1} is missing ${key}`);
  }
  if (!isCategory(item.category)) throw new Error(`Evidence item ${index + 1} has an invalid category`);
  for (const key of ["published_at", "captured_at", "payment_signal", "buyer_type", "problem", "urgency_signal"]) {
    if (item[key] !== undefined && item[key] !== null && typeof item[key] !== "string") throw new Error(`Evidence item ${index + 1} has an invalid ${key}`);
  }
  return item as EvidenceInput;
}

export function parseEvidenceImport(text: string): EvidenceInput[] {
  let payload: unknown;
  try { payload = JSON.parse(text); } catch { throw new Error("Import must be valid JSON"); }
  if (!Array.isArray(payload)) throw new Error("Import must be a JSON array");
  return payload.map(validateInput);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getAccessToken();
  if (!token) throw new Error("Please sign in before using the evidence inbox.");
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...init.headers },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string; error?: { message?: string } } | null;
    throw new Error(payload?.error?.message ?? payload?.detail ?? `Evidence request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export async function fetchEvidence(category: EvidenceCategory, limit = 100): Promise<EvidenceRecord[]> {
  return request<EvidenceRecord[]>(buildEvidenceQuery(category, limit));
}

export async function uploadEvidence(batchId: string, items: EvidenceInput[]): Promise<EvidenceBatchResult> {
  return request<EvidenceBatchResult>("/api/intelligence/evidence/batches", {
    method: "POST",
    body: JSON.stringify({ batch_id: batchId, items }),
  });
}

export async function fetchEvidenceRuntime(): Promise<EvidenceRuntime> {
  return request<EvidenceRuntime>("/api/intelligence/evidence/runtime");
}

export async function fetchAcquisitionMetrics(): Promise<AcquisitionMetrics> {
  return request<AcquisitionMetrics>("/api/dashboard/acquisition");
}
export async function collectEvidence(source: EvidenceSource, query: string, manualConfirmed: boolean, cursor?: string, requestId?: string, batchId?:string|null, config?:{freshness_hours:number;policy:CollectionPolicy}): Promise<EvidenceCollectResult> {
  const params = new URLSearchParams({ source, query });
  return request<EvidenceCollectResult>(`/api/intelligence/evidence/collect?${params.toString()}`, {
    method: "POST",
    body: JSON.stringify({ manual_confirmed: manualConfirmed, ...(cursor ? {cursor} : {}), ...(requestId ? {request_id:requestId} : {}), ...(batchId ? {billing_batch_id:batchId} : {}), ...config }),
  });
}

export type EvidenceReviewInput = { verification_status?: string; category?: EvidenceCategory; notes?: string; title?: string; summary?: string; budget_min?: number | null; budget_max?: number | null; assessment?: Partial<Pick<DemandAssessment,"availability"|"payment"|"eligibility">>; label_group?: string };
export async function exportEvidenceLabels():Promise<{rows:unknown[];count:number;target:number}> {
  return request("/api/intelligence/evidence/labels");
}
export async function reviewEvidence(evidenceId: string, input: EvidenceReviewInput): Promise<EvidenceRecord> {
  return request<EvidenceRecord>(`/api/intelligence/evidence/${evidenceId}/review`, { method: "PATCH", body: JSON.stringify(input) });
}
export async function convertEvidence(evidenceId: string, input: Pick<EvidenceReviewInput, "title" | "summary" | "budget_min" | "budget_max"> = {}) {
  return request<Record<string, unknown>>(`/api/intelligence/evidence/${evidenceId}/convert`, { method: "POST", body: JSON.stringify(input) });
}
