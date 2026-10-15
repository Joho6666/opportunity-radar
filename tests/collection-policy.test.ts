import { describe, expect, it } from "vitest";
import { DEFAULT_COLLECTION_POLICY, policyKey, splitTerms, validPolicy } from "@/lib/collection-policy";
import { collectionAttempt } from "@/lib/evidence-client";
import { toRadar } from "@/lib/transform";

describe("collection configuration",()=>{
  it("accepts Chinese and English delimiters without duplicate queries",()=>{
    expect(splitTerms("PPT，Word,简历；PPT\n网站")).toEqual(["PPT","Word","简历","网站"]);
  });
  it("binds idempotency to every filter and time window",()=>{
    const key=policyKey(DEFAULT_COLLECTION_POLICY,72);
    const first=collectionAttempt(null,"rss","PPT",undefined,undefined,key);
    expect(collectionAttempt(first,"rss","PPT",undefined,undefined,key).requestId).toBe(first.requestId);
    for (const change of [{sort:"hot" as const},{excluded_terms:["教程"]},{activity_filter:"author" as const},{include_unknown_dates:true}]) {
      expect(collectionAttempt(first,"rss","PPT",undefined,undefined,policyKey({...DEFAULT_COLLECTION_POLICY,...change},72)).requestId).not.toBe(first.requestId);
    }
    expect(collectionAttempt(first,"rss","PPT",undefined,undefined,policyKey(DEFAULT_COLLECTION_POLICY,24)).requestId).not.toBe(first.requestId);
  });
  it("keeps persisted policy and actual queries in the Radar client",()=>{
    const raw={id:"r",collection_policy:DEFAULT_COLLECTION_POLICY,freshness_hours:24,queries:[{source:"rss",query:"feed"}]};
    const radar=toRadar(raw);
    expect(radar.collectionPolicy).toEqual(DEFAULT_COLLECTION_POLICY);
    expect(radar.freshnessHours).toBe(24);
    expect(radar.queries).toEqual(raw.queries);
    expect(validPolicy({...DEFAULT_COLLECTION_POLICY,required_terms:["x".repeat(101)]})).toBe(false);
    expect(toRadar({...raw,frequency:"manual",next_run_at:"2027-01-01T00:00:00Z"}).nextRunAt).toBe("手动运行");
  });
});
