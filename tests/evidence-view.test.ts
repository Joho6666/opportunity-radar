import { describe, expect, it } from "vitest";
import type { EvidenceRecord } from "@/lib/evidence-client";
import { authorOf, countBy, sourceOf, sourcesIn, draftOpportunity, parseBudget, reasonLabel, statusOf, visibleRecords, evidenceBudgetLabel } from "@/lib/evidence-view";

function record(id: string, overrides: Partial<EvidenceRecord> = {}): EvidenceRecord {
  return { evidence_id: id, source: "tiktok", url: `https://example.test/${id}`, raw_text: `text ${id}`, published_at: null, captured_at: "2026-10-13T00:00:00Z", category: "buyer", payment_signal: null, verification_status: "unverified", ...overrides };
}

describe("evidence view helpers", () => {
  it("shows only source-extracted budgets and leaves absent currency unknown", () => {
    expect(evidenceBudgetLabel(record("a",{payment_signal:"预算"}))).toBe("预算未知");
    expect(evidenceBudgetLabel(record("b",{metadata:{facts:JSON.stringify({budget_min:500,budget_max:800,currency:"USD"})}}))).toBe("预算 USD 500–800");
    expect(evidenceBudgetLabel(record("c",{metadata:{facts:JSON.stringify({budget_min:2000,budget_max:2000,currency:null})}}))).toBe("预算 币种未知 2000");
  });
  it("translates rule reason codes and keeps unknown ones", () => {
    expect(reasonLabel("seller_self_promotion")).toBe("卖方自荐，不是买方");
    expect(reasonLabel("custom_code")).toBe("custom_code");
    expect(reasonLabel(undefined)).toBe("未记录");
  });

  it("pending queue drops reviewed items so it shrinks as you work", () => {
    const records = [record("a"), record("b", { verification_status: "verified" }), record("c", { verification_status: "invalidated" }), record("d", { category: "market" })];
    expect(visibleRecords(records, { category: "buyer", status: "pending", search: "", sort: "grade" }).map((r) => r.evidence_id)).toEqual(["a"]);
    expect(countBy(records, "buyer")).toEqual({ pending: 1, verified: 1, invalidated: 1, all: 3 });
  });

  it("grade sort puts A first, then higher confidence", () => {
    const records = [record("c", { evidence_grade: "C" }), record("a-low", { evidence_grade: "A", classification_confidence: 0.6 }), record("a-high", { evidence_grade: "A", classification_confidence: 0.9 })];
    expect(visibleRecords(records, { category: "buyer", status: "all", search: "", sort: "grade" }).map((r) => r.evidence_id)).toEqual(["a-high", "a-low", "c"]);
  });

  it("search matches text and notes, case-insensitively", () => {
    const records = [record("a", { raw_text: "Need a Shopify developer" }), record("b", { notes: "老客户转介绍" })];
    expect(visibleRecords(records, { category: "buyer", status: "all", search: "shopify", sort: "grade" }).map((r) => r.evidence_id)).toEqual(["a"]);
    expect(visibleRecords(records, { category: "buyer", status: "all", search: "转介绍", sort: "grade" }).map((r) => r.evidence_id)).toEqual(["b"]);
  });

  it("drafts a short title from the first clause and keeps the full text as summary", () => {
    const draft = draftOpportunity(record("a", { raw_text: "求推荐靠谱的外包团队做小程序，预算2万，月底前交付" }));
    expect(draft.title).toBe("求推荐靠谱的外包团队做小程序");
    expect(draft.summary).toBe("求推荐靠谱的外包团队做小程序，预算2万，月底前交付");
  });

  it("treats unknown status as pending and validates budgets", () => {
    expect(statusOf(record("a", { verification_status: "weird" }))).toBe("unverified");
    expect(parseBudget("")).toBeNull();
    expect(parseBudget("3000")).toBe(3000);
    expect(parseBudget("-1")).toBe("invalid");
    expect(parseBudget("2万")).toBe("invalid");
  });
});

describe("pinning the record being converted", () => {
  it("keeps a just-verified record in the pending view while its form is open", () => {
    const records = [record("a", { verification_status: "verified" }), record("b")];
    expect(visibleRecords(records, { category: "buyer", status: "pending", search: "", sort: "grade" }).map((r) => r.evidence_id)).toEqual(["b"]);
    expect(visibleRecords(records, { category: "buyer", status: "pending", search: "", sort: "grade", keep: "a" }).map((r) => r.evidence_id).sort()).toEqual(["a", "b"]);
  });
});

describe("source display and filter", () => {
  it("names RSS items after their site and filters by source", () => {
    const v2ex = record("a", { source: "rss", url: "https://www.v2ex.com/t/1", metadata: { raw_author: " 老王 " } });
    const dy = record("b", { source: "douyin", source_platform: "douyin" });
    const dy2 = record("c", { source: "douyin", source_platform: "douyin" });
    expect(sourceOf(v2ex).label).toBe("V2EX");
    expect(authorOf(v2ex)).toBe("老王");
    expect(authorOf(dy)).toBeNull();
    expect(sourcesIn([v2ex, dy, dy2], "buyer").map((s) => [s.label, s.count])).toEqual([["抖音", 2], ["V2EX", 1]]);
    expect(visibleRecords([v2ex, dy, dy2], { category: "buyer", status: "all", search: "", sort: "grade", source: "v2ex.com" }).map((r) => r.evidence_id)).toEqual(["a"]);
  });
});
