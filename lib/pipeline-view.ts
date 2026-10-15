import type { Opportunity } from "@/types/domain";
export function matchesFollowUp(item: Pick<Opportunity,"status"|"pipeline">, filter: string, now = new Date()): boolean {
  if (filter === "all") return true;
  if (["won","lost","ignored"].includes(item.status)) return false;
  const due = new Date(String(item.pipeline?.next_follow_up_at ?? ""));
  if (Number.isNaN(due.getTime())) return false;
  if (filter === "overdue") return due.getTime() < now.getTime();
  return filter === "today" && due.getFullYear() === now.getFullYear() && due.getMonth() === now.getMonth() && due.getDate() === now.getDate();
}
