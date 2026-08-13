import { describe, expect, it } from "vitest";
import { mockOpportunities } from "@/data/mock-opportunities";
import { parseRadarIntent } from "@/services/radar.service";

describe("Opportunity Radar mock domain", () => {
  it("sorts the recommended opportunity above lower-scored opportunities", () => {
    const sorted = [...mockOpportunities].sort((a, b) => b.opportunityScore - a.opportunityScore);
    expect(sorted[0]?.id).toBe("ppt-guilin");
  });
  it("creates an API-ready radar intent from natural-language input", async () => {
    const result = await parseRadarIntent("寻找桂林的 PPT 需求");
    expect(result.minimumBudget).toBe(200);
    expect(result.keywords).toContain("PPT");
  });
});
