import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs));
export const yuan = (value: number) => value ? `¥${value.toLocaleString("zh-CN")}` : "面议";
