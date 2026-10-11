import { describe, expect, it } from "vitest";
import {
  buildEvidenceQuery,
  parseEvidenceImport,
  type EvidenceRecord,
} from "@/lib/evidence-client";

describe("evidence client parsing", () => {
  it("parses a JSON array and preserves nullable fields", () => {
    const record: EvidenceRecord = {
      evidence_id: "ev-1",
      source: "Reddit",
      url: "https://example.com/post",
      raw_text: "We pay contractors for this problem.",
      published_at: null,
      captured_at: "2026-10-11T10:00:00Z",
      category: "buyer",
      payment_signal: "paid pilot",
      verification_status: "unverified",
    };

    expect(parseEvidenceImport(JSON.stringify([record]))).toEqual([record]);
  });

  it("rejects malformed or non-array imports", () => {
    expect(() => parseEvidenceImport("not json")).toThrow("valid JSON");
    expect(() => parseEvidenceImport(JSON.stringify({ evidence_id: "ev-1" }))).toThrow(
      "JSON array",
    );
  });

  it("rejects imports that are missing required evidence fields", () => {
    expect(() => parseEvidenceImport(JSON.stringify([{ evidence_id: "ev-1" }]))).toThrow(
      "raw_text",
    );
  });

  it("builds the category and limit query", () => {
    expect(buildEvidenceQuery("market", 25)).toBe(
      "/api/intelligence/evidence?category=market&limit=25",
    );
  });
});
