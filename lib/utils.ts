import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
export const yuan = (value: number) => value ? `¥${value.toLocaleString("zh-CN")}` : "面议";

export function budgetLabel(item: {budgetUnknown?: boolean; budgetMin: number; budgetMax: number; currency: string}) {
  if (item.budgetUnknown) return "预算未知";
  const prefix = item.currency === "CNY" ? "¥" : item.currency === "USD" ? "$" : "币种未知 ";
  return `${prefix}${item.budgetMin.toLocaleString("zh-CN")}–${prefix}${item.budgetMax.toLocaleString("zh-CN")}`;
}
