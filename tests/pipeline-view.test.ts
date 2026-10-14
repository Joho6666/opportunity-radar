import { describe,it,expect } from "vitest";
import { matchesFollowUp } from "../lib/pipeline-view";
describe("manual follow-up queue",()=>{
  it("uses local calendar boundaries and excludes closed leads",()=>{
    const now=new Date(2026,9,14,12);
    const due=new Date(2026,9,14,9).toISOString();
    expect(matchesFollowUp({status:"verified",pipeline:{next_follow_up_at:due}},"today",now)).toBe(true);
    expect(matchesFollowUp({status:"verified",pipeline:{next_follow_up_at:due}},"overdue",now)).toBe(true);
    expect(matchesFollowUp({status:"won",pipeline:{next_follow_up_at:due}},"today",now)).toBe(false);
    expect(matchesFollowUp({status:"new",pipeline:{}},"today",now)).toBe(false);
  });
});
