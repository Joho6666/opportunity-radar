import { expect, it } from "vitest";
import { DEFAULT_IDENTITY, IDENTITY_BUSINESS_PRESETS, identityToRadarPrefill, validateIdentity, type LocalIdentity } from "../lib/identity";

const IDENTITY: LocalIdentity = {
  businesses: [
    { id: "video", name: "AI 电商视频 / 广告", remote_deliverable: true },
    { id: "web", name: "小程序 / 网站轻开发", remote_deliverable: false },
  ],
  target_roles: ["电商商家", "品牌方", "代运营工作室", "独立卖家"],
  service_mode: "regions",
  regions: ["深圳"],
  default_freshness_hours: 168,
  preferred_sources: ["xiaohongshu", "douyin"],
  buyer_keywords: ["找人做视频", "求视频制作", "视频外包", "第四个词"],
  exclude_words: ["教程", "招聘", "承接"],
  business_match_words: ["视频", "信息流"],
  quote_style: "先确认需求量与交期，再给区间报价。",
};

it("默认身份不预置敏感属性，只含公开经营角色信息", () => {
  expect(DEFAULT_IDENTITY.businesses).toEqual([]);
  expect(DEFAULT_IDENTITY.exclude_words).toEqual([]);
  expect(DEFAULT_IDENTITY.default_freshness_hours).toBe(168);
  expect(Object.keys(DEFAULT_IDENTITY)).toEqual([
    "businesses", "target_roles", "service_mode", "regions", "default_freshness_hours",
    "preferred_sources", "buyer_keywords", "exclude_words", "business_match_words", "quote_style",
  ]);
});

it("生成抓单预填：关键词≤3、业务词、角色过滤枚举、排除词、时效与平台", () => {
  const prefill = identityToRadarPrefill(IDENTITY, ["xiaohongshu", "douyin", "zhihu"]);
  expect(prefill.presetId).toBe("video");
  expect(prefill.keywords).toEqual(["找人做视频", "求视频制作", "视频外包"]);
  expect(prefill.businessTerms).toEqual(["视频", "信息流"]);
  expect(prefill.excludes).toEqual(["教程", "招聘", "承接"]);
  expect(prefill.hours).toBe(168);
  expect(prefill.sources).toEqual(["xiaohongshu", "douyin"]);
  expect(prefill.roles).toEqual(["电商商家", "品牌方", "代运营工作室"]);
  expect(prefill.regions).toEqual(["深圳"]);
  expect(prefill.match_mode).toBe("local");
});

it("远程/不限身份不写地区；全远程业务保持远程优先", () => {
  const remote = identityToRadarPrefill({ ...IDENTITY, service_mode: "remote", businesses: [{ id: "video", name: "AI 电商视频 / 广告", remote_deliverable: true }] }, ["xiaohongshu"]);
  expect(remote.regions).toEqual([]);
  expect(remote.match_mode).toBe("remote");
  const unspecified = identityToRadarPrefill({ ...IDENTITY, service_mode: "unspecified" }, []);
  expect(unspecified.sources).toEqual([]);
  expect(unspecified.match_mode).toBe("remote");
});

it("平台预填只保留当前可选平台", () => {
  const prefill = identityToRadarPrefill(IDENTITY, ["douyin"]);
  expect(prefill.sources).toEqual(["douyin"]);
});

it("无身份时返回空预填，不影响原表单", () => {
  const prefill = identityToRadarPrefill(null, []);
  expect(prefill).toEqual({ presetId: undefined, keywords: [], businessTerms: [], excludes: [], hours: undefined, sources: [], roles: [], regions: [], match_mode: "remote" });
});

it("越界输入在保存前被拒绝", () => {
  expect(validateIdentity(IDENTITY)).toBeNull();
  expect(validateIdentity({ ...IDENTITY, target_roles: ["x".repeat(21)] })).toContain("角色");
  expect(validateIdentity({ ...IDENTITY, regions: [] })).toContain("地区");
  expect(validateIdentity({ ...IDENTITY, businesses: Array.from({ length: 11 }, (_, index) => ({ id: `b${index}`, name: "业务", remote_deliverable: true })) })).toContain("业务");
  expect(validateIdentity({ ...IDENTITY, buyer_keywords: ["x".repeat(101)] })).toContain("关键词");
  expect(validateIdentity({ ...IDENTITY, exclude_words: Array.from({ length: 21 }, () => "词") })).toContain("排除词");
  expect(validateIdentity({ ...IDENTITY, preferred_sources: ["不存在的平台"] })).toContain("平台");
  expect(validateIdentity({ ...IDENTITY, quote_style: "长".repeat(501) })).toContain("风格");
  expect(IDENTITY_BUSINESS_PRESETS.map((item) => item.id)).toEqual(["video", "drama", "web", "office", "workflow"]);
});
