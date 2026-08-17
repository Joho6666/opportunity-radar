import type { Opportunity, OpportunityType } from "@/types/domain";

export type OpportunitySort = "AI 推荐" | "最新" | "预算" | "风险";

export function filterOpportunities(items: Opportunity[], options: { query?: string; type?: OpportunityType | "all"; sort?: OpportunitySort }): Opportunity[] {
  const { query = "", type = "all", sort = "AI 推荐" } = options;
  const keyword = query.trim().toLowerCase();
  return items
    .filter((x) => (type === "all" || x.type === type) && `${x.title}${x.summary}${x.skills.join("")}`.toLowerCase().includes(keyword))
    .sort((a, b) => sort === "最新" ? b.publishedAt.localeCompare(a.publishedAt) : sort === "预算" ? b.budgetMax - a.budgetMax : sort === "风险" ? a.riskScore - b.riskScore : b.opportunityScore - a.opportunityScore);
}
