import { describe, expect, it } from "vitest";
import { fromProfile, toBrief, toOpportunity, toProfile, toRadar } from "@/lib/transform";
import { mockProfile } from "@/data/mock-profile";

describe("backend field transforms", () => {
  it("maps OpportunityRead to the frontend shape", () => {
    const raw = { id: "o1", type: "client", title: "PPT", summary: "s", source: "mock", source_url: "https://example.com", published_at: "2026-08-01T10:00:00Z", location: "桂林", work_mode: "online", budget_min: 200, budget_max: 300, estimated_hours: 3, estimated_hourly_rate: [66, 100], match_score: 96, opportunity_score: 91, conversion_probability: 82, risk_score: 18, recommendation: "强烈推荐", status: "new", skills: ["PPT"], reasons: ["r"], warnings: ["w"] };
    const item = toOpportunity(raw);
    expect(item.type).toBe("client");
    expect(item.workMode).toBe("线上");
    expect(item.budgetMax).toBe(300);
    expect(item.status).toBe("new");
    expect(item.publishedAt).not.toBe("未知时间");
  });
  it("maps RadarRead including stats and status", () => {
    const raw = { id: "r1", name: "雷达", description: "", goal: "g", status: "active", keywords: ["PPT"], locations: ["桂林"], minimum_budget: 200, frequency: "daily", last_run_at: null, next_run_at: null, stats: { items_found: 8, opportunities_found: 4, matched: 3, recommended: 2 } };
    const radar = toRadar(raw);
    expect(radar.status).toBe("active");
    expect(radar.stats).toEqual({ scanned: 8, found: 4, matched: 3, recommended: 2 });
    expect(radar.lastRunAt).toBe("未运行");
  });
  it("keeps paused and running statuses distinct from active", () => {
    expect(toRadar({ id: "r2", name: "x", status: "paused", stats: {} }).status).toBe("paused");
    expect(toRadar({ id: "r3", name: "x", status: "running", stats: {} }).status).toBe("running");
  });
  it("round-trips profile payloads", () => {
    const payload = fromProfile(mockProfile);
    expect(payload.display_name).toBe(mockProfile.name);
    expect(payload.skills[0]).toEqual({ name: "PPT", level: "strong" });
    const back = toProfile({ display_name: "小何", identity: "", location: "桂林", monthly_income_goal: 6000, minimum_project_budget: 200, available_hours_per_day: 4, skills: [{ name: "PPT", level: "strong" }], goals: ["client", "job"] });
    expect(back.name).toBe("小何");
    expect(back.skillLevels["PPT"]).toBe("擅长");
    expect(back.goals).toEqual(["找客户", "找工作"]);
  });
  it("maps the daily brief", () => {
    const brief = toBrief({ scanned_count: 100, opportunities_count: 5, recommended_count: 2, potential_income_min: 1000, potential_income_max: 2000, signals: ["趋势"], avoid: ["注意"], actions: ["行动"] });
    expect(brief.potentialIncome).toEqual([1000, 2000]);
    expect(brief.avoid).toBe("注意");
  });
});
