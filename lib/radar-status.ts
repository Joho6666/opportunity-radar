import type { Radar } from "@/types/domain";

export const radarStatusLabel: Record<Radar["status"], string> = {
  active: "已启用",
  running: "扫描中",
  paused: "已暂停",
  error: "异常",
};

export function radarStatusClass(status: Radar["status"]): string {
  return status === "running" || status === "active" ? "text-xs text-signal" : "text-xs text-muted";
}

export function isRadarEnabled(status: Radar["status"]): boolean {
  return status === "active" || status === "running";
}
