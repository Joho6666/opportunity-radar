import { describe, expect, it } from "vitest";
import { BUSINESS_PRESETS, buildLeadRadar, estimateHunt, groupHuntSources, platformQueries, selectAllAvailable, shortenDouyinKeyword, WECHAT_SCOPES, type HuntSource } from "../lib/lead-hunt";

const catalog: HuntSource[] = [
  { id: "xiaohongshu", name: "小红书", available: true, status: "可运行 · 已实测", detail: "", provider: "tikhub", selectable: true, price_usd: 0.01, live_verified: true },
  { id: "wechat_search", name: "微信搜一搜", available: true, status: "可运行 · 已实测", detail: "", provider: "tikhub", selectable: true, price_usd: 0.01, live_verified: true },
  { id: "wechat_mp", name: "微信公众号", available: false, status: "已覆盖 · 搜一搜垂类", detail: "", provider: "tikhub", selectable: false, covered_by: "wechat_search", vertical: "article" },
  { id: "wechat_channels", name: "微信视频号", available: false, status: "已覆盖 · 搜一搜垂类", detail: "", provider: "tikhub", selectable: false, covered_by: "wechat_search", vertical: "video" },
  { id: "toutiao", name: "今日头条", available: false, status: "待接入", detail: "", provider: "tikhub", selectable: false },
  { id: "instagram", name: "Instagram", available: false, status: "不适用", detail: "", provider: "tikhub", selectable: false },
  { id: "github", name: "GitHub", available: true, status: "公开来源 · 待运行", detail: "", provider: "public", selectable: true, price_usd: null },
  { id: "rss", name: "RSS", available: true, status: "公开来源 · 待运行", detail: "", provider: "public", selectable: true, price_usd: null },
  { id: "web_search", name: "网页搜索", available: false, status: "未配置", detail: "", provider: "firecrawl", selectable: true },
];

describe("平台分组与全选", () => {
  it("把可用、被垂类覆盖、不可用与网页搜索分开，不把不可用卡片混进主区", () => {
    const groups = groupHuntSources(catalog);
    expect(groups.available.map(item => item.id)).toEqual(["xiaohongshu", "wechat_search", "github", "rss"]);
    expect(groups.covered.map(item => item.id)).toEqual(["wechat_mp", "wechat_channels"]);
    expect(groups.unavailable.map(item => item.id)).toEqual(["toutiao", "instagram"]);
    expect(groups.web.map(item => item.id)).toEqual(["web_search"]);
  });
  it("全选只选可用平台（含免费公开来源），不选被覆盖或待接入项", () => {
    expect(selectAllAvailable(catalog)).toEqual(["xiaohongshu", "wechat_search", "github", "rss"]);
    expect(selectAllAvailable([])).toEqual([]);
  });
});

describe("请求与费用估算", () => {
  it("按 关键词×平台 估算请求数，公开来源计 0 美元", () => {
    const result = estimateHunt({ catalog, sources: ["xiaohongshu", "wechat_search", "github"], keywords: ["找人做视频", "求视频制作"] });
    expect(result.perPlatform).toBe(2);
    expect(result.requests).toBe(6);
    expect(result.costUsd).toBeCloseTo(0.04, 6);
    expect(result.paidSources).toEqual(["xiaohongshu", "wechat_search"]);
    expect(result.freeSources).toEqual(["github"]);
    expect(result.exceedsDaily).toBe(false);
  });
  it("平台多时受 6 次首屏上限约束，按每平台 1 个词计算并提示", () => {
    const result = estimateHunt({ catalog, sources: ["xiaohongshu", "wechat_search", "github", "rss"], keywords: ["一", "二", "三"] });
    expect(result.perPlatform).toBe(1);
    expect(result.requests).toBe(4);
    expect(result.truncatedKeywords).toBe(true);
    expect(result.note).toContain("6 次首屏");
  });
  it("超过每日剩余请求或单轮 USD 0.10 时给出阻断提示", () => {
    expect(estimateHunt({ catalog, sources: ["xiaohongshu"], keywords: ["找人做视频", "求视频制作", "视频外包"], remainingRequests: 2 }).exceedsDaily).toBe(true);
    expect(estimateHunt({ catalog, sources: ["xiaohongshu", "wechat_search"], keywords: ["一", "二", "三"], singleRunLimitUsd: 0.05 }).exceedsDaily).toBe(true);
    expect(estimateHunt({ catalog, sources: ["xiaohongshu"], keywords: ["找人做视频"], remainingCostUsd: 0.005 }).exceedsDaily).toBe(true);
  });
  it("超过 6 个平台时直接判为超限，不显示 0 次请求的成功假象", () => {
    const result = estimateHunt({ catalog, sources: Array.from({ length: 7 }, () => "xiaohongshu"), keywords: ["找人做视频"] });
    expect(result.overPlatformCap).toBe(true);
    expect(result.exceedsDaily).toBe(true);
    expect(result.note).toContain("超过每轮 6 次");
  });
});

describe("微信垂类配置", () => {
  it("提供综合/文章/视频三个范围，并把选择写入 source_config", () => {
    expect(WECHAT_SCOPES.map(scope => scope.id)).toEqual(["all", "article", "video"]);
    const payload = buildLeadRadar(BUSINESS_PRESETS[0], ["wechat_search"], "找人做视频", 168, "", BUSINESS_PRESETS[0].terms, undefined, [], "video");
    expect(payload.source_config.wechat_business_type).toBe("video");
    const other = buildLeadRadar(BUSINESS_PRESETS[0], ["xiaohongshu"], "找人做视频", 168);
    expect(other.source_config.wechat_business_type).toBeUndefined();
  });
  it("每个业务预设都有 3 个可一键填入的关键词模板", () => {
    for (const preset of BUSINESS_PRESETS) {
      expect(preset.keywordTemplates).toHaveLength(3);
      expect(preset.keywordTemplates.every(template => template.trim().length > 0 && template.split(/[，,]/).length <= 3)).toBe(true);
    }
  });
});

describe("平台级关键词适配", () => {
  it("抖音截短为核心 2–4 字，小红书保留长短语；依据父代理已核实证据", () => {
    expect(shortenDouyinKeyword("家居 找视频拍摄")).toBe("家居");
    expect(shortenDouyinKeyword("圣诞 视频 制作 求推荐")).toBe("圣诞");
    expect(shortenDouyinKeyword("找人做电商视频")).toBe("电商视频");
    expect(shortenDouyinKeyword("桂林 找人做视频")).toBe("视频");
    const groups = platformQueries(["家居 找视频拍摄", "找人做电商视频"], ["douyin", "xiaohongshu"], ["深圳"]);
    expect(groups).toEqual([
      { source: "douyin", queries: ["家居", "电商视频"] },
      { source: "xiaohongshu", queries: ["家居 找视频拍摄", "找人做电商视频", "深圳 家居 找视频拍摄"] },
    ]);
    expect(groups.reduce((total, group) => total + group.queries.length, 0)).toBe(5);
  });
  it("抖音短词去重后减少请求数，估算与预览一致", () => {
    const merged = platformQueries(["家居 找视频拍摄", "家居 找人做视频"], ["douyin"]);
    expect(merged[0].queries).toEqual(["家居"]);
    const result = estimateHunt({ catalog, sources: ["douyin", "xiaohongshu"], keywords: ["家居 找视频拍摄", "家居 找人做视频"] });
    expect(result.requests).toBe(3);
    expect(result.note).not.toContain("超过");
  });
});

describe("精简抓单请求", () => {
  it("保留平台、买方查询和发布窗口，关闭定时及自动 AI", () => {
    const payload = buildLeadRadar(BUSINESS_PRESETS[0], ["xiaohongshu", "douyin"], "求 电商视频，找人做广告", 720);
    expect(payload.sources).toEqual(["xiaohongshu", "douyin"]);
    expect(payload.keywords).toEqual(["求 电商视频", "找人做广告"]);
    expect(payload.frequency).toBe("manual");
    expect(payload.local_schedule_enabled).toBe(false);
    expect(payload.mode).toBe("general");
    expect(payload.freshness_hours).toBe(720);
    expect(payload.source_config).toMatchObject({ lead_hunt: "true", freshness_hours: "720" });
    expect(payload.collection_policy.time_basis).toBe("published");
    expect(payload.collection_policy.include_unknown_dates).toBe(false);
    expect(payload.collection_policy.required_terms).toEqual(BUSINESS_PRESETS[0].terms);
  });
  it("拒绝过量查询而非静默丢关键词", () => {
    expect(() => buildLeadRadar(BUSINESS_PRESETS[0], ["douyin"], "一，二，三，四", 168)).toThrow();
    expect(() => buildLeadRadar(BUSINESS_PRESETS[0], [], "找人", 168)).toThrow();
  });
  it("排除词写入 collection_policy 参与后端过滤，越界即拒绝", () => {
    const payload = buildLeadRadar(BUSINESS_PRESETS[0], ["xiaohongshu"], "找人做视频", 168, "", BUSINESS_PRESETS[0].terms, undefined, ["教程", "招聘", "承接"]);
    expect(payload.collection_policy.excluded_terms).toEqual(["教程", "招聘", "承接"]);
    expect(() => buildLeadRadar(BUSINESS_PRESETS[0], ["xiaohongshu"], "找人做视频", 168, "", BUSINESS_PRESETS[0].terms, undefined, Array.from({ length: 21 }, () => "词"))).toThrow("排除词");
  });
});
