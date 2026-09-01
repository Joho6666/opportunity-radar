import type { Radar } from "@/types/domain";
export const mockRadars: Radar[] = [
  { id: "client-radar", name: "客户机会雷达", description: "持续寻找 PPT、AI 自动化和网站开发需求。", status: "active", goal: "寻找桂林和线上、预算 200 元以上的客户需求", keywords: ["PPT", "AI 自动化", "网站开发"], locations: ["桂林", "线上"], minimumBudget: 200, frequency: "每天", sources: ["xiaohongshu", "web", "forum"], lastRunAt: "12 分钟前", nextRunAt: "明天 09:00", stats: { scanned: 6840, found: 49, matched: 17, recommended: 6 } },
  { id: "job-radar", name: "求职雷达", description: "筛选远程 AI 实习和自动化岗位。", status: "active", goal: "寻找远程 AI 自动化实习与兼职岗位", keywords: ["Python", "n8n", "AI Agent"], locations: ["远程"], minimumBudget: 2500, frequency: "每天", sources: ["boss", "web"], lastRunAt: "27 分钟前", nextRunAt: "明天 09:00", stats: { scanned: 3821, found: 32, matched: 12, recommended: 2 } },
  { id: "github-radar", name: "GitHub 项目雷达", description: "发现适合参与的中文 AI 开源项目。", status: "paused", goal: "寻找可以快速参与并积累作品集的 AI Agent 项目", keywords: ["AI Agent", "中文", "Python"], locations: ["远程"], minimumBudget: 0, frequency: "每周", sources: ["github"], lastRunAt: "3 天前", nextRunAt: "暂停中", stats: { scanned: 1820, found: 20, matched: 8, recommended: 1 } }
];
