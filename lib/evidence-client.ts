import { getAccessToken } from "@/lib/auth";

export const EVIDENCE_CATEGORIES = ["buyer", "content", "market"] as const;
export type EvidenceCategory = (typeof EVIDENCE_CATEGORIES)[number];

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
  batch_id: string;
  inserted: number;
  duplicates: number;
  records: EvidenceRecord[];
};

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
