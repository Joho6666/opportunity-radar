import { describe, expect, it } from "vitest";
import {
  BUSINESS_PRESETS, buildLeadRadar, estimateHunt, parseTelegramChannels, parseToutiaoLinks,
  platformQueries, type HuntSource,
} from "../lib/lead-hunt";

const catalog: HuntSource[] = [
  { id: "wechat_search", name: "微信搜一搜", available: true, status: "可运行", detail: "", provider: "tikhub", selectable: true, price_usd: 0.01, extra_call_price_usd: 0.01, extra_calls_per_item: 2 },
  { id: "telegram", name: "Telegram", available: true, status: "可运行", detail: "", provider: "tikhub", selectable: true, price_usd: 0.001, mode: "channel_search" },
  { id: "linkedin", name: "LinkedIn", available: true, status: "可运行", detail: "", provider: "tikhub", selectable: true, price_usd: 0.05, mode: "hiring_signal" },
  { id: "toutiao", name: "今日头条", available: true, status: "可运行", detail: "", provider: "tikhub", selectable: true, price_usd: 0.001, mode: "link_import" },
];

describe("four platform mode inputs", () => {
  it("parses Telegram channel usernames from @name, t.me URLs and commas", () => {
    expect(parseTelegramChannels("@Foo, https://t.me/bar\nbaz")).toEqual(["Foo", "bar", "baz"]);
    expect(parseTelegramChannels("bad name!, @ok_name")).toEqual(["bad", "ok_name"]);
    expect(parseTelegramChannels("")).toEqual([]);
  });

  it("parses only Toutiao article links and keeps the numeric id", () => {
    const links = parseToutiaoLinks("https://www.toutiao.com/article/7450114952884503059/\nhttps://m.toutiao.com/article/7450114952884503059/?source=x");
    expect(links).toEqual([
      { id: "7450114952884503059", url: "https://www.toutiao.com/article/7450114952884503059/" },
    ]);
    expect(parseToutiaoLinks("https://example.com/article/123")).toEqual([]);
    expect(parseToutiaoLinks("https://www.toutiao.com/video/7450114952884503059/")).toEqual([]);
  });

  it("special modes consume one keyword slot, not one slot per keyword", () => {
    const plan = platformQueries(["视频制作", "剪辑", "外包"], ["telegram", "reddit"]);
    expect(plan).toEqual([
      { source: "telegram", queries: ["视频制作"] },
      { source: "reddit", queries: ["视频制作", "剪辑", "外包"] },
    ]);
  });
});

describe("estimate includes extra paid calls", () => {
  it("counts WeChat share-chain detail + share calls per item", () => {
    const estimate = estimateHunt({ catalog, sources: ["wechat_search"], keywords: ["视频制作"], wechatScope: "video", wechatShareCount: 3 });
    expect(estimate.requests).toBe(7); // 1 search + 2 calls * 3 links
    expect(estimate.costUsd).toBeCloseTo(0.07, 6);
    expect(estimate.note).toContain("分享链");
  });

  it("counts one request per Telegram channel and Toutiao link", () => {
    const telegram = estimateHunt({ catalog, sources: ["telegram"], keywords: ["视频制作"], telegramChannels: "@alpha,@beta,@gamma" });
    expect(telegram.requests).toBe(3);
    expect(telegram.costUsd).toBeCloseTo(0.003, 6);
    const toutiao = estimateHunt({ catalog, sources: ["toutiao"], keywords: ["视频制作"], toutiaoLinks: "https://www.toutiao.com/article/7450114952884503059/\nhttps://www.toutiao.com/article/7450114952884503060/" });
    expect(toutiao.requests).toBe(2);
    expect(toutiao.costUsd).toBeCloseTo(0.002, 6);
    const linkedin = estimateHunt({ catalog, sources: ["linkedin"], keywords: ["视频制作"] });
    expect(linkedin.requests).toBe(1);
    expect(linkedin.costUsd).toBeCloseTo(0.05, 6);
  });

  it("refuses more than ten calls per run", () => {
    const estimate = estimateHunt({ catalog, sources: ["wechat_search"], keywords: ["视频制作"], wechatScope: "video", wechatShareCount: 3, remainingRequests: 4 });
    expect(estimate.overCallCap).toBe(false);
    expect(estimate.overDailyRequests).toBe(true);
  });
});

describe("buildLeadRadar refuses modes without their required input", () => {
  const preset = BUSINESS_PRESETS[0];
  it("rejects Telegram without channels and Toutiao without links", () => {
    expect(() => buildLeadRadar(preset, ["telegram"], "视频制作", 168, "", preset.terms, undefined, [], "article", { telegramChannels: [] })).toThrow(/频道/);
    expect(() => buildLeadRadar(preset, ["toutiao"], "视频制作", 168, "", preset.terms, undefined, [], "article", { toutiaoLinks: [] })).toThrow(/链接/);
  });

  it("writes the mode inputs into source_config", () => {
    const radar = buildLeadRadar(preset, ["telegram", "toutiao"], "视频制作", 168, "", preset.terms, undefined, [], "article", {
      telegramChannels: ["Foo", "bar"],
      toutiaoLinks: [{ id: "7450114952884503059", url: "https://www.toutiao.com/article/7450114952884503059/" }],
    });
    expect(radar.source_config.telegram_channels).toBe("Foo,bar");
    expect(radar.source_config.toutiao_links).toBe("https://www.toutiao.com/article/7450114952884503059/");
    expect(radar.keywords).toEqual(["视频制作"]);
  });

  it("writes WeChat share count only in video scope", () => {
    const video = buildLeadRadar(preset, ["wechat_search"], "视频制作", 168, "", preset.terms, undefined, [], "video", { wechatShareCount: 2 });
    expect(video.source_config.wechat_share_links).toBe("2");
    const article = buildLeadRadar(preset, ["wechat_search"], "视频制作", 168, "", preset.terms, undefined, [], "article", { wechatShareCount: 2 });
    expect(article.source_config.wechat_share_links).toBeUndefined();
  });
});
