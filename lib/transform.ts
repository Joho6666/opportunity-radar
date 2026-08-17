import type { DailyBrief, Opportunity, OpportunityStatus, OpportunityType, Profile, Radar, WorkMode } from "@/types/domain";

const workModeMap: Record<string, WorkMode> = { online: "线上", offline: "线下", hybrid: "混合" };
const levelMap: Record<string, Profile["skillLevels"][string]> = { beginner: "入门", intermediate: "熟练", strong: "擅长", expert: "专家" };
const levelReverse: Record<Profile["skillLevels"][string], string> = { 入门: "beginner", 熟练: "intermediate", 擅长: "strong", 专家: "expert" };
const goalMap: Record<string, Profile["goals"][number] & string> = { job: "找工作", client: "找客户", project: "找项目", business: "找商业机会" };
const goalReverse: Record<string, string> = { 找工作: "job", 找客户: "client", 找项目: "project", 找商业机会: "business" };

function formatDateTime(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? fallback : new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function toOpportunity(raw: any): Opportunity {
  return { id: raw.id, type: (raw.type ?? "project") as OpportunityType, title: raw.title, summary: raw.summary, source: raw.source === "mock" ? "Mock 数据源" : raw.source, sourceUrl: raw.source_url, sourceType: mapSourceType(raw.source), publishedAt: formatDateTime(raw.published_at, "未知时间"), location: raw.location, workMode: workModeMap[raw.work_mode] ?? "线上", budgetMin: raw.budget_min ?? 0, budgetMax: raw.budget_max ?? 0, currency: "CNY", estimatedHours: raw.estimated_hours ?? 0, estimatedHourlyRate: [raw.estimated_hourly_rate?.[0] ?? 0, raw.estimated_hourly_rate?.[1] ?? 0], matchScore: raw.match_score ?? 0, opportunityScore: raw.opportunity_score ?? 0, conversionProbability: raw.conversion_probability ?? 0, riskScore: raw.risk_score ?? 0, recommendation: raw.recommendation ?? "一般", skills: raw.skills ?? [], reasons: raw.reasons ?? [], warnings: raw.warnings ?? [], status: (raw.status ?? "new") as OpportunityStatus, deadline: raw.deadline ?? "未知", workload: raw.workload ?? "以沟通为准" };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function toRadar(raw: any): Radar {
  const status = raw.status === "paused" ? "paused" : raw.status === "error" ? "error" : "running";
  return { id: raw.id, name: raw.name, description: raw.description ?? "", status, goal: raw.goal ?? "", keywords: raw.keywords ?? [], locations: raw.locations ?? [], minimumBudget: raw.minimum_budget ?? 0, frequency: raw.frequency ?? "每天", sources: (raw.sources ?? ["mock"]) as Radar["sources"], lastRunAt: formatDateTime(raw.last_run_at, "未运行"), nextRunAt: formatDateTime(raw.next_run_at, "—"), stats: { scanned: raw.stats?.items_found ?? 0, found: raw.stats?.opportunities_found ?? 0, matched: raw.stats?.matched ?? 0, recommended: raw.stats?.recommended ?? 0 } };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function toProfile(raw: any, previous?: Profile): Profile {
  const skills = (raw.skills ?? []) as { name: string; level: string }[];
  const skillLevels: Profile["skillLevels"] = {};
  for (const skill of skills) skillLevels[skill.name] = levelMap[skill.level] ?? "熟练";
  return { name: raw.display_name ?? previous?.name ?? "新用户", identity: raw.identity ?? "", skills: skills.map((s) => s.name), skillLevels, goals: (raw.goals ?? []).map((g: string) => goalMap[g] ?? g), location: raw.location ?? previous?.location ?? "", workModes: previous?.workModes ?? ["线上", "混合"], monthlyIncomeGoal: raw.monthly_income_goal ?? 0, minimumProjectBudget: raw.minimum_project_budget ?? 0, availableHoursPerDay: raw.available_hours_per_day ?? 0, excludedOpportunityTypes: previous?.excludedOpportunityTypes ?? [] };
}

export function fromProfile(profile: Profile) {
  return { display_name: profile.name || "新用户", identity: profile.identity ?? "", location: profile.location ?? "", monthly_income_goal: profile.monthlyIncomeGoal ?? 0, minimum_project_budget: profile.minimumProjectBudget ?? 0, available_hours_per_day: profile.availableHoursPerDay ?? 0, skills: profile.skills.map((name) => ({ name, level: levelReverse[profile.skillLevels[name]] ?? "intermediate" })), goals: profile.goals.map((goal) => goalReverse[goal] ?? "client").filter((goal): goal is string => Boolean(goal)) };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function toBrief(raw: any, scannedFallback = 0): DailyBrief {
  return { scanned: raw?.scanned_count ?? scannedFallback, found: raw?.opportunities_count ?? 0, recommended: raw?.recommended_count ?? 0, potentialIncome: [raw?.potential_income_min ?? 0, raw?.potential_income_max ?? 0], trends: raw?.signals ?? [], avoid: (raw?.avoid ?? []).join("；"), actions: raw?.actions ?? [] };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function mapSourceType(source: any): Opportunity["sourceType"] {
  const value = String(source ?? "");
  const validSources: Opportunity["sourceType"][] = ["xiaohongshu", "boss", "github", "reddit", "web", "forum"];
  if ((validSources as readonly string[]).includes(value)) return value as Opportunity["sourceType"];
  if (value.includes("github")) return "github";
  return "web";
}

export const statusActionMap: Record<OpportunityStatus, string | null> = { new: null, saved: "save", contacted: "contact", negotiating: "negotiate", won: "win", lost: "lose", ignored: "ignore" };
