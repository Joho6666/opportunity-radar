import {describe,it,expect} from "vitest";
import {toOpportunity} from "@/lib/transform";
import {budgetLabel} from "@/lib/utils";

describe("acquisition source facts",()=>{
  it("preserves source currency and unknown hours",()=>{
    const item=toOpportunity({id:"x",evidence_id:"e",budget_min:500,budget_max:800,metadata:{currency:"USD",hours_unknown:true},verification_status:"unverified"});
    expect(item.currency).toBe("USD");expect(budgetLabel(item)).toBe("$500–$800");expect(item.hoursUnknown).toBe(true);
    expect(item.actualRevenue).toBeUndefined();expect(item.verificationStatus).toBe("unverified");
  });
  it("does not infer currency or a known budget",()=>{
    const item=toOpportunity({id:"x",evidence_id:"e",metadata:{budget_unknown:true}});
    expect(item.currency).toBe("未知币种");expect(budgetLabel(item)).toBe("预算未知");
  });
});
