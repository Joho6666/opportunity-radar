export type CollectionPolicy = {
  required_terms: string[];
  excluded_terms: string[];
  match_mode: "any" | "all";
  time_basis: "published" | "activity";
  include_unknown_dates: boolean;
  sort: "latest" | "hot";
  activity_filter: "any" | "author" | "discussion";
  min_interactions: number;
};

export const DEFAULT_COLLECTION_POLICY: CollectionPolicy = {
  required_terms: [], excluded_terms: [], match_mode: "any", time_basis: "published",
  include_unknown_dates: false, sort: "latest", activity_filter: "any", min_interactions: 0,
};

export function splitTerms(value: string): string[] {
  return [...new Set(value.split(/[,，、;；\n]/).map(x => x.trim()).filter(Boolean))];
}

/** Stable field order for request identity even after loading persisted JSON. */
export function policyKey(policy: CollectionPolicy, hours: number): string {
  return JSON.stringify([hours, policy.required_terms, policy.excluded_terms, policy.match_mode,
    policy.time_basis, policy.include_unknown_dates, policy.sort, policy.activity_filter, policy.min_interactions]);
}

export function validPolicy(policy: CollectionPolicy): boolean {
  return [policy.required_terms, policy.excluded_terms].every(terms => terms.length <= 20 && terms.every(t => t.length <= 100))
    && Number.isInteger(policy.min_interactions) && policy.min_interactions >= 0 && policy.min_interactions <= 10000000;
}
