import { mockRadars } from "@/data/mock-radars";
export async function listRadars() { return mockRadars; }
export async function parseRadarIntent(input: string) { return { name: "兼职客户雷达", description: input, keywords: ["PPT", "AI 自动化", "小程序"], locations: ["桂林", "线上"], minimumBudget: 200 }; }
