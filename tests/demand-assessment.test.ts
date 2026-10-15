import {describe,it,expect} from "vitest";
import {visibleRecords,evidenceBudgetLabel} from "../lib/evidence-view";
import type {EvidenceRecord} from "../lib/evidence-client";

describe("actionable demand view",()=>{
  it("keeps closed requests outside the default queue but preserves all view",()=>{
    const row={evidence_id:"x",raw_text:"找人做PPT，需求已取消",category:"buyer",verification_status:"unverified",assessment:{actionable_candidate:false}} as EvidenceRecord;
    expect(visibleRecords([row],{category:"buyer",status:"pending",search:"",sort:"grade"})).toHaveLength(0);
    expect(visibleRecords([row],{category:"buyer",status:"all",search:"",sort:"grade"})).toHaveLength(1);
  });
  it("does not disguise a lower budget bound as a fixed amount",()=>{
    const row={evidence_id:"budget",source:"rss",url:"https://example.test",raw_text:"",published_at:null,captured_at:"",category:"buyer",payment_signal:null,verification_status:"unverified",metadata:{facts:JSON.stringify({budget_min:5000,budget_max:null,budget_bound:"lower",currency:null})}} as EvidenceRecord;
    expect(evidenceBudgetLabel(row)).toContain("5000+");
  });
});
