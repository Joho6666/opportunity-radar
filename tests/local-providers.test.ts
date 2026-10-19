import { expect, it } from "vitest";
import { authorizationFromBudgets, confirmMessage, approveRun, readBudgets, type ProviderBudgets } from "../lib/local-providers";

const BUDGETS: ProviderBudgets = { single_run_limit_usd: 0.1, daily_limit_usd: 1, daily_request_limit: 20, confirm_required: true };

it("预算映射为手动采集授权请求，绝不越过每日请求上限", () => {
  expect(authorizationFromBudgets(BUDGETS)).toEqual({ run_requests: 10, daily_requests: 20, run_cost_usd: 0.1, daily_cost_usd: 1 });
  const tight = authorizationFromBudgets({ ...BUDGETS, daily_request_limit: 3, single_run_limit_usd: 0.05, daily_limit_usd: 0.5 });
  expect(tight).toEqual({ run_requests: 3, daily_requests: 3, run_cost_usd: 0.05, daily_cost_usd: 0.5 });
});

it("读取预算时有本地硬上限兜底，缺字段回退默认值", () => {
  const fallback = readBudgets({});
  expect(fallback).toEqual(BUDGETS);
  const clamped = readBudgets({ daily_limit_usd: 99, daily_request_limit: 999, single_run_limit_usd: 99 });
  expect(clamped.daily_limit_usd).toBe(1);
  expect(clamped.daily_request_limit).toBe(20);
  expect(clamped.single_run_limit_usd).toBe(1);
  expect(clamped.single_run_limit_usd).toBeLessThanOrEqual(clamped.daily_limit_usd);
});

it("需要确认时给出包含金额与次数上限的确认文案；关闭后直接放行", () => {
  expect(confirmMessage(BUDGETS)).toContain("USD 0.1");
  expect(confirmMessage(BUDGETS)).toContain("20");
  let asked = "";
  expect(approveRun(BUDGETS, (message) => { asked = message; return false; })).toBe(false);
  expect(asked).toContain("确认");
  expect(approveRun({ ...BUDGETS, confirm_required: false }, () => { throw new Error("不应询问"); })).toBe(true);
});
