import { describe, expect, it } from "vitest";
import { filterOpportunities } from "@/lib/filters";
import { mockOpportunities } from "@/data/mock-opportunities";
import type { Opportunity } from "@/types/domain";

const sample = (overrides: Partial<Opportunity>): Opportunity => ({ ...mockOpportunities[0], ...overrides });

describe("filterOpportunities", () => {
  it("filters by opportunity type", () => {
    const items = [sample({ id: "1", type: "job" }), sample({ id: "2", type: "client" }), sample({ id: "3", type: "github" })];
    expect(filterOpportunities(items, { type: "job" }).map((x) => x.id)).toEqual(["1"]);
    expect(filterOpportunities(items, { type: "client" }).map((x) => x.id)).toEqual(["2"]);
    expect(filterOpportunities(items, { type: "github" }).map((x) => x.id)).toEqual(["3"]);
    expect(filterOpportunities(items, { type: "all" })).toHaveLength(3);
  });
  it("filters by keyword across title, summary and skills", () => {
    const items = [sample({ id: "1", title: "桂林 PPT" }), sample({ id: "2", title: "其他", summary: "包含 n8n 自动化" }), sample({ id: "3", title: "无关", skills: ["STM32"] })];
    expect(filterOpportunities(items, { query: "n8n" }).map((x) => x.id)).toEqual(["2"]);
    expect(filterOpportunities(items, { query: "stm32" }).map((x) => x.id)).toEqual(["3"]);
    expect(filterOpportunities(items, { query: "不存在" })).toHaveLength(0);
  });
  it("sorts by latest, budget, risk and AI recommendation", () => {
    const items = [
      sample({ id: "a", publishedAt: "1", budgetMax: 100, riskScore: 50, opportunityScore: 60 }),
      sample({ id: "b", publishedAt: "2", budgetMax: 300, riskScore: 80, opportunityScore: 90 }),
      sample({ id: "c", publishedAt: "3", budgetMax: 200, riskScore: 10, opportunityScore: 75 })
    ];
    expect(filterOpportunities(items, { sort: "最新" }).map((x) => x.id)).toEqual(["c", "b", "a"]);
    expect(filterOpportunities(items, { sort: "预算" }).map((x) => x.id)).toEqual(["b", "c", "a"]);
    expect(filterOpportunities(items, { sort: "风险" }).map((x) => x.id)).toEqual(["c", "a", "b"]);
    expect(filterOpportunities(items, { sort: "AI 推荐" }).map((x) => x.id)).toEqual(["b", "c", "a"]);
  });
});
