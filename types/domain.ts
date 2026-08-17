export type OpportunityType = "job" | "client" | "project" | "business" | "github";
export type OpportunityStatus = "new" | "saved" | "contacted" | "negotiating" | "won" | "lost" | "ignored";
export type WorkMode = "线上" | "线下" | "混合";
export type SourceType = "xiaohongshu" | "boss" | "github" | "reddit" | "web" | "forum";
export type Recommendation = "强烈推荐" | "值得考虑" | "一般" | "不建议";
export interface Opportunity { id: string; type: OpportunityType; title: string; summary: string; source: string; sourceUrl: string; sourceType: SourceType; publishedAt: string; location: string; workMode: WorkMode; budgetMin: number; budgetMax: number; currency: "CNY"; estimatedHours: number; estimatedHourlyRate: [number, number]; matchScore: number; opportunityScore: number; conversionProbability: number; riskScore: number; recommendation: Recommendation; skills: string[]; reasons: string[]; warnings: string[]; status: OpportunityStatus; deadline: string; workload: string; actualRevenue?: number; }
export interface Radar { id: string; name: string; description: string; status: "running" | "paused" | "error"; goal: string; keywords: string[]; locations: string[]; minimumBudget: number; frequency: string; sources: SourceType[]; lastRunAt: string; nextRunAt: string; stats: { scanned: number; found: number; matched: number; recommended: number }; }
export interface Profile { name: string; identity: string; skills: string[]; skillLevels: Record<string, "入门" | "熟练" | "擅长" | "专家">; goals: string[]; location: string; workModes: WorkMode[]; monthlyIncomeGoal: number; minimumProjectBudget: number; availableHoursPerDay: number; excludedOpportunityTypes: OpportunityType[]; }
export interface Skill { id: string; name: string; description: string; installed: boolean; icon: string; }
export interface DailyBrief { scanned: number; found: number; recommended: number; potentialIncome: [number, number]; trends: string[]; avoid: string; actions: string[]; }
