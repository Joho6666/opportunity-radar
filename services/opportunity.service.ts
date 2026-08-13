import { mockOpportunities } from "@/data/mock-opportunities";
export async function listOpportunities() { return mockOpportunities; }
export async function analyzeOpportunity(id: string) { return mockOpportunities.find((item) => item.id === id); }
