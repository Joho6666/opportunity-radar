import { DEFAULT_COLLECTION_POLICY, splitTerms } from "./collection-policy";
import { allRegionNames, regionLabel } from "./region-tree";

export const BUSINESS_PRESETS = [
  {
    id: "video", name: "AI 电商视频 / 广告", keywords: "找人做电商视频，求广告视频制作",
    terms: ["电商", "商品", "带货", "广告", "产品视频", "信息流", "视频素材", "亚马逊", "AI视频", "视频生成"],
    keywordTemplates: ["找人做电商视频, 求产品视频制作", "求广告视频外包, 短视频批量制作", "找人复刻视频, 求AI视频制作"],
  },
  {
    id: "drama", name: "视频复刻 / AI 短剧", keywords: "找人复刻视频，求AI短剧制作",
    terms: ["复刻", "短剧", "视频", "AI剧"],
    keywordTemplates: ["找人做AI短剧, 求短剧制作", "求视频复刻, 找人做口播视频", "短剧外包, 求AI分镜制作"],
  },
  {
    id: "web", name: "小程序 / 网站轻开发", keywords: "找人开发小程序，网站外包需求",
    terms: ["小程序", "网站", "网页", "落地页", "官网"],
    keywordTemplates: ["找人开发小程序, 求网站外包", "求落地页开发, 官网外包", "找人做微信小程序, 求网页开发"],
  },
  {
    id: "office", name: "PPT / Word / Excel", keywords: "求做PPT，找人做Excel",
    terms: ["PPT", "Word", "Excel", "演示文稿", "表格", "文档"],
    keywordTemplates: ["求做PPT, 找人做Excel", "求Word排版, 演示文稿外包", "表格处理外包, 找人做文档"],
  },
  {
    id: "workflow", name: "Skill / 工作流自动化", keywords: "求工作流自动化，找人做AI工作流",
    terms: ["自动化", "工作流", "Skill", "Agent", "n8n"],
    keywordTemplates: ["求工作流自动化, 找人做AI工作流", "n8n自动化外包, 求Agent开发", "求Skill开发, 工作流搭建"],
  },
];
export type BusinessPreset = typeof BUSINESS_PRESETS[number];

export type WechatScope = "all" | "article" | "video";
export type WechatScopeState = "verified" | "untested" | "unavailable";
export const WECHAT_SCOPES: { id: WechatScope; label: string; state: WechatScopeState; hint: string }[] = [
  { id: "all", label: "综合", state: "untested", hint: "官方支持；本轮未单独实测，可能混入无原文链接的视频条目" },
  { id: "article", label: "公众号文章", state: "verified", hint: "已实测 35 条：标题/公众号/发布时间/原文链接齐全" },
  { id: "video", label: "视频号视频", state: "verified", hint: "已实测：搜索→详情→分享链；每条额外 2 次调用 +USD0.02，单条约 30 秒" },
];
export const DEFAULT_WECHAT_SCOPE: WechatScope = "article";
export function wechatScopeMeta(id: WechatScope) { return WECHAT_SCOPES.find(scope => scope.id === id) ?? WECHAT_SCOPES[1]; }

/** 特殊受限模式：一次运行只发一个查询单元，内部再按频道/链接展开。 */
export const SPECIAL_SOURCES = new Set(["telegram", "linkedin", "toutiao"]);
export const BASE_QUERY_CAP = 6;
export const MAX_RUN_REQUESTS = 10;

export function parseTelegramChannels(value: string): string[] {
  const tokens = (value || "").split(/[\s,，;；]+/).filter(Boolean);
  if (tokens.length > 3) return [];
  const channels: string[] = [];
  for (const token of tokens) {
    const match = token.match(/^(?:https?:\/\/)?(?:www\.)?(?:t\.me|telegram\.me)\/([^/?#]+)/i);
    const name = (match ? match[1] : token.replace(/^@/, "")).replace(/\/+$/, "");
    if (!/^[A-Za-z0-9_]{3,64}$/.test(name)) continue;
    if (!channels.includes(name)) channels.push(name);
  }
  return channels;
}
export function telegramChannelError(value: string): string {
  const tokens = (value || "").split(/[\s,，;；]+/).filter(Boolean);
  if (tokens.length > 3) return "Telegram 最多填写 3 个频道用户名。";
  if (!parseTelegramChannels(value).length) return "请先填写 1–3 个公开频道用户名（如 @channel）。未填频道不能选中 Telegram。";
  return "";
}

export function parseToutiaoLinks(value: string): { id: string; url: string }[] {
  const tokens = (value || "").split(/[\s,，;；]+/).filter(Boolean);
  if (tokens.length > 3) return [];
  const links: { id: string; url: string }[] = [];
  for (const token of tokens) {
    let parsed: URL;
    try { parsed = new URL(token); } catch { continue; }
    const host = parsed.hostname.toLowerCase();
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") continue;
    if (host !== "toutiao.com" && !host.endsWith(".toutiao.com")) continue;
    const match = parsed.pathname.match(/^\/article\/(\d+)\/?$/);
    if (!match) continue;
    if (links.some(link => link.id === match[1])) continue;
    links.push({ id: match[1], url: `https://www.toutiao.com/article/${match[1]}/` });
  }
  return links;
}
export function toutiaoLinkError(value: string): string {
  const tokens = (value || "").split(/[\s,，;；]+/).filter(Boolean);
  if (tokens.length > 3) return "今日头条最多填写 3 条文章链接。";
  if (!parseToutiaoLinks(value).length) return "请先粘贴 1–3 条 https://www.toutiao.com/article/<id>/ 链接。未填链接不能选中今日头条。";
  return "";
}

export type HuntModeConfig = {
  wechatShareCount?: number; telegramChannels?: string[]; toutiaoLinks?: { id: string; url: string }[];
};

export type HuntSource = {
  id: string; name: string; available: boolean; status: string; detail: string; selectable?: boolean;
  provider?: string; live_verified?: boolean; price_usd?: number | null; time_policy?: string;
  api_capabilities?: { keyword_search: boolean; detail: boolean; comments: boolean };
  implemented_capabilities?: { search: boolean; detail: boolean; comments: boolean };
  covered_by?: string; vertical?: string; covered_request_id?: string; validation_status?: string;
  supports_scope_selector?: boolean; native_time_filter?: { supported: boolean; verified: boolean; values: string[] };
  verticals?: { id: WechatScope; label: string; status: string; verified: boolean; request_id?: string; total?: number; rows?: number; reason?: string }[];
  mode?: string; mode_label?: string; verified?: boolean; request_id?: string; requires?: string[]; limits?: string;
  modes?: { id: string; label: string; verified: boolean; price_usd?: number | null; extra_price_usd?: number | null;
    extra_calls_per_item?: number; request_id?: string; requires?: string[]; limits?: string }[];
  share_link?: { verified: boolean; extra_price_usd?: number | null; calls_per_item?: number; timeout_seconds?: number;
    limits?: string; chain?: string; search_request_id?: string; detail_request_id?: string; share_request_id?: string; share_url?: string };
  extra_call_price_usd?: number | null; extra_calls_per_item?: number;
};
export function isHuntSourceSelectable(source: HuntSource) { return source.selectable !== false; }

// 抖音对长短语几乎零召回。父代理 2026-10-18 真实调用证据：
// 「找拍摄」→8 条、「家居」→1000 条；「家居 找视频拍摄」→0、「圣诞 视频 制作 求推荐」→0。
// 本规则据此截短，本轮未重新付费验证（见 backend/tests/fixtures/tikhub_live/douyin_short_keyword_evidence.json）。
const DOUYIN_CITY_NAMES = new Set(["北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安", "南京", "苏州", "天津",
  "长沙", "郑州", "东莞", "佛山", "宁波", "青岛", "合肥", "昆明", "福州", "厦门", "济南", "大连", "沈阳", "哈尔滨", "长春",
  "石家庄", "太原", "南昌", "贵阳", "南宁", "海口", "兰州", "西宁", "银川", "乌鲁木齐", "呼和浩特", "拉萨", "桂林", "柳州",
  "珠海", "中山", "惠州", "汕头", "温州", "嘉兴", "绍兴", "台州", "金华", "泉州", "烟台", "潍坊", "徐州", "常州", "南通",
  "扬州", "洛阳"]);
const REGION_QUERY_SKIP = new Set([...DOUYIN_CITY_NAMES, ...allRegionNames()]);
const DOUYIN_LEADING = ["找人", "求推荐", "求", "需要", "想找", "帮我", "有没有", "哪里", "怎么", "做一个", "做"];
const DOUYIN_TRAILING = ["制作", "拍摄", "剪辑", "外包", "需求", "推荐", "开发", "设计", "服务", "团队", "公司"];

export function shortenDouyinKeyword(value: string): string {
  const tokens = (value || "").split(/[\s，,、/|]+/).filter(Boolean);
  const kept = tokens.filter(token => !REGION_QUERY_SKIP.has(token) && !/^.{2,4}[市省区县]$/.test(token));
  for (const token of (kept.length ? kept : tokens)) {
    let core = token.replace(/^[，,。.！!？?、/|:：;；()（）[\]【】"'“”]+|[，,。.！!？?、/|:：;；()（）[\]【】"'“”]+$/g, "");
    let changed = true;
    while (changed) {
      changed = false;
      for (const prefix of DOUYIN_LEADING) {
        if (core.startsWith(prefix) && core.length - prefix.length >= 2) { core = core.slice(prefix.length); changed = true; break; }
      }
    }
    while (core.length > 4) {
      const suffix = DOUYIN_TRAILING.find(item => core.endsWith(item) && core.length - item.length >= 2);
      if (!suffix) break;
      core = core.slice(0, -suffix.length);
    }
    if (core.length > 4) core = core.slice(0, 4);
    if (core.length >= 2 && core.length <= 4) return core;
  }
  return "";
}

export type PlatformQueryGroup = { source: string; queries: string[] };
/** 与原先后端 hunt_topics 一致：每平台词数受 6 次首屏限制；抖音只发短词，去重后计数。 */
export function platformQueries(keywords: string[], sources: string[], regions: string[] = [], wechatScope: WechatScope = "article"): PlatformQueryGroup[] {
  const limit = Math.min(3, Math.floor(BASE_QUERY_CAP / Math.max(1, sources.length)));
  const unique = (items: string[]) => [...new Set(items.filter(Boolean))];
  return sources.map(source => {
    if (source === "douyin") {
      return { source, queries: unique(keywords.map(shortenDouyinKeyword)).slice(0, limit) };
    }
    // 受限模式由采集器在内部展开频道/链接/职位，只保留一个查询单元，
    // 否则会按关键词重复付费。
    if (SPECIAL_SOURCES.has(source) || (source === "wechat_search" && wechatScope === "video")) {
      return { source, queries: unique(keywords).slice(0, 1) };
    }
    const topics = keywords.slice(0, limit);
    if (regions.length && topics.length && limit >= 2) {
      const variant = `${regions[0]} ${topics[0]}`;
      if (topics.length < limit) topics.push(variant);
      else topics[topics.length - 1] = variant;
    }
    return { source, queries: unique(topics) };
  });
}

/** 三个真实分组：可运行、被垂类覆盖、不可用；付费网页搜索单列，不混进公开来源。 */
export type HuntSourceGroups = { available: HuntSource[]; covered: HuntSource[]; unavailable: HuntSource[]; web: HuntSource[] };
export function groupHuntSources(catalog: HuntSource[]): HuntSourceGroups {
  const groups: HuntSourceGroups = { available: [], covered: [], unavailable: [], web: [] };
  for (const source of catalog) {
    if (source.provider === "firecrawl") groups.web.push(source);
    else if (source.covered_by) groups.covered.push(source);
    else if (isHuntSourceSelectable(source)) groups.available.push(source);
    else groups.unavailable.push(source);
  }
  return groups;
}
export function selectAllAvailable(catalog: HuntSource[]) { return groupHuntSources(catalog).available.map(source => source.id); }

export type HuntEstimateInput = {
  catalog: HuntSource[]; sources: string[]; keywords: string[]; remainingRequests?: number; remainingCostUsd?: number;
  singleRunLimitUsd?: number; region?: string; regions?: string[]; wechatScope?: WechatScope; wechatShareCount?: number;
  telegramChannels?: string; toutiaoLinks?: string;
};
export type HuntEstimate = {
  perPlatform: number; requests: number; extraRequests: number; costUsd: number; paidSources: string[]; freeSources: string[];
  unknownPriceSources: string[]; overPlatformCap: boolean; overCallCap: boolean; exceedsDaily: boolean; overBudget: boolean;
  overDailyRequests: boolean; overDailyCost: boolean; truncatedKeywords: boolean; note: string;
};
/** 6 次首屏查询 + 视频号分享链/频道/链接附加调用；费用只按已核验单价累加。 */
export function estimateHunt({ catalog, sources, keywords, remainingRequests, remainingCostUsd,
  singleRunLimitUsd = 0.1, region, regions, wechatScope = "article", wechatShareCount = 1,
  telegramChannels = "", toutiaoLinks = "" }: HuntEstimateInput): HuntEstimate {
  const selected = sources.map(id => catalog.find(source => source.id === id)).filter((source): source is HuntSource => Boolean(source));
  const plan = platformQueries(keywords, sources, regions ?? (region ? [region] : []), wechatScope);
  const baseRequests = plan.reduce((total, group) => total + group.queries.length, 0);
  const baseSlots = sources.reduce((total, source) => total + (SPECIAL_SOURCES.has(source) || (source === "wechat_search" && wechatScope === "video") ? 1 : keywords.length), 0);
  const overPlatformCap = sources.length > 6 || baseSlots > BASE_QUERY_CAP;
  const perPlatform = Math.min(keywords.length, Math.min(3, Math.max(0, Math.floor(BASE_QUERY_CAP / Math.max(1, sources.length)))));
  const channels = parseTelegramChannels(telegramChannels);
  const links = parseToutiaoLinks(toutiaoLinks);
  const shareCount = [1, 2, 3].includes(wechatShareCount) ? wechatShareCount : 1;
  let extraRequests = 0;
  if (sources.includes("telegram")) extraRequests += Math.max(0, channels.length - 1);
  if (sources.includes("toutiao")) extraRequests += Math.max(0, links.length - 1);
  if (sources.includes("wechat_search") && wechatScope === "video") extraRequests += 2 * shareCount;
  const requests = baseRequests + extraRequests;
  const paidSources: string[] = [];
  const freeSources: string[] = [];
  const unknownPriceSources: string[] = [];
  for (const source of selected) {
    if (typeof source.price_usd === "number") {
      if (source.price_usd > 0) paidSources.push(source.id);
      else freeSources.push(source.id);
    } else if (source.provider === "firecrawl") unknownPriceSources.push(source.id);
    else freeSources.push(source.id);
  }
  let cost = plan.reduce((total, group) => {
    const price = selected.find(source => source.id === group.source)?.price_usd;
    return total + (typeof price === "number" ? price * group.queries.length : 0);
  }, 0);
  const telegramPrice = selected.find(source => source.id === "telegram")?.price_usd;
  const toutiaoPrice = selected.find(source => source.id === "toutiao")?.price_usd;
  const wechat = selected.find(source => source.id === "wechat_search");
  if (sources.includes("telegram") && typeof telegramPrice === "number") cost += telegramPrice * Math.max(0, channels.length - 1);
  if (sources.includes("toutiao") && typeof toutiaoPrice === "number") cost += toutiaoPrice * Math.max(0, links.length - 1);
  if (sources.includes("wechat_search") && wechatScope === "video" && typeof wechat?.extra_call_price_usd === "number") {
    cost += wechat.extra_call_price_usd * 2 * shareCount;
  }
  const costUsd = Number(cost.toFixed(6));
  const overBudget = costUsd > singleRunLimitUsd + 1e-9;
  const overCallCap = requests > MAX_RUN_REQUESTS;
  const overDailyRequests = remainingRequests !== undefined && requests > remainingRequests;
  const overDailyCost = remainingCostUsd !== undefined && costUsd > remainingCostUsd + 1e-9;
  const truncatedKeywords = keywords.length > 0 && perPlatform < keywords.length;
  const notes: string[] = [];
  if (overPlatformCap) notes.push(`已选 ${sources.length} 个平台，超过每轮 ${BASE_QUERY_CAP} 次首屏查询上限；请减少平台。`);
  else if (!sources.length) notes.push("先选至少一个平台。");
  else if (!keywords.length) notes.push("先填 1–3 个买方关键词。");
  if (truncatedKeywords && !overPlatformCap) notes.push(`受每轮 ${BASE_QUERY_CAP} 次首屏上限约束，每平台只取前 ${perPlatform} 个关键词。`);
  if (extraRequests > 0) notes.push(`含附加调用 ${extraRequests} 次（视频号分享链每条 2 次 / 每个频道 1 次 / 每条头条链接 1 次），本轮共 ${requests} 次。`);
  if (overCallCap) notes.push(`本轮需要 ${requests} 次调用，超过每轮 ${MAX_RUN_REQUESTS} 次硬上限；请减少平台或分享链条数。`);
  if (overBudget) notes.push(`本次约 USD ${costUsd.toFixed(3)}，超过单轮上限 USD ${singleRunLimitUsd.toFixed(2)}。`);
  if (overDailyRequests) notes.push(`本日仅剩 ${remainingRequests} 次请求，本次需要 ${requests} 次。`);
  if (overDailyCost) notes.push(`本日剩余额度约 USD ${(remainingCostUsd ?? 0).toFixed(3)}，本次约 USD ${costUsd.toFixed(3)}。`);
  if (unknownPriceSources.length) notes.push(`含未核验单价的付费来源（${unknownPriceSources.join("、")}），费用以平台账单为准。`);
  if (region && sources.length * perPlatform >= 1) notes.push("含地区变体时只替换后续查询，不增加请求数。");
  return { perPlatform, requests, extraRequests, costUsd, paidSources, freeSources, unknownPriceSources, overPlatformCap,
    overCallCap, exceedsDaily: overPlatformCap || overCallCap || overBudget || overDailyRequests || overDailyCost,
    overBudget, overDailyRequests, overDailyCost, truncatedKeywords, note: notes.join(" ") };
}

export const HUNT_ROLE_GROUPS = [
  { label: "商家", roles: ["电商商家", "品牌方", "实体店"] },
  { label: "团队", roles: ["创业者", "代运营工作室", "市场团队", "培训机构"] },
  { label: "个人", roles: ["学生", "自由职业", "自媒体"] },
];
export const HUNT_ROLES = HUNT_ROLE_GROUPS.flatMap(group => group.roles);
export const HUNT_INTENT_GROUPS = [
  { label: "正在采购", intents: ["找人制作", "询价报价"] },
  { label: "还在了解", intents: ["咨询方案"] },
  { label: "希望持续", intents: ["长期合作"] },
];
export const HUNT_INTENTS = HUNT_INTENT_GROUPS.flatMap(group => group.intents);
export type HuntConditions = { regions: string[]; roles: string[]; intents: string[]; match_mode: "local" | "remote" | "keep_unknown"; start_at?: string; end_at?: string };
export const DEFAULT_HUNT_CONDITIONS: HuntConditions = { regions: [], roles: [], intents: [], match_mode: "remote" };
export function shanghaiToUtc(value: string) { return new Date(`${value}:00+08:00`).toISOString(); }
export function utcToShanghaiInput(value?: string) { return value ? new Date(new Date(value).getTime() + 8 * 3600000).toISOString().slice(0,16) : ""; }
export function readHuntConditions(config: Record<string,string>): HuntConditions { try { return config.hunt_conditions ? JSON.parse(config.hunt_conditions) : DEFAULT_HUNT_CONDITIONS; } catch { return DEFAULT_HUNT_CONDITIONS; } }
export function describeHuntConditions(config: Record<string,string>) {
  if (!config.hunt_conditions) return "旧版配置，尚未启用条件匹配";
  const c=readHuntConditions(config);
  const time=c.start_at ? `${utcToShanghaiInput(c.start_at).replace("T"," ")} 至 ${utcToShanghaiInput(c.end_at).replace("T"," ")}（上海时间）` : `${config.freshness_hours || "168"}小时内`;
  return `${time} · ${c.regions.map(regionLabel).join("；") || "全国"} · ${c.roles.join(" / ") || "角色不限"} · ${c.intents.join(" / ") || "意图不限"} · ${{local:"严格本地",remote:"远程优先",keep_unknown:"保留未知"}[c.match_mode]}`;
}
export function previewHuntQueries(keywords: string[], sources: string[], conditions: HuntConditions) {
  const limit = Math.min(3, Math.floor(6 / Math.max(1,sources.length)));
  const topics = keywords.slice(0,limit);
  if (conditions.regions.length && topics.length && limit >= 2) { const variant = `${conditions.regions[0]} ${topics[0]}`; if (topics.length < limit) topics.push(variant); else topics[topics.length-1] = variant; }
  return topics;
}
export function buildLeadRadar(preset: BusinessPreset, sources: string[], value: string, hours: number, feedUrl = "", businessTerms = preset.terms, conditions?: HuntConditions, excludedTerms: string[] = [], wechatScope: WechatScope = DEFAULT_WECHAT_SCOPE, modes: HuntModeConfig = {}) {
  const keywords = splitTerms(value);
  const channels = modes.telegramChannels ?? [];
  const links = modes.toutiaoLinks ?? [];
  const shareCount = modes.wechatShareCount ?? 1;
  if (!sources.length || !keywords.length || keywords.length > 3 || keywords.some(term => term.length > 100)) throw new Error("请选择平台，填写 1–3 个买方关键词。");
  if (sources.includes("telegram") && !channels.length) throw new Error("Telegram 需填写 1–3 个频道用户名；未填频道不能选中。");
  if (sources.includes("toutiao") && !links.length) throw new Error("今日头条需粘贴 1–3 条文章链接；未填链接不能选中。");
  if (sources.includes("wechat_search") && wechatScope === "video" && ![1, 2, 3].includes(shareCount)) throw new Error("视频号分享链条数只能是 1–3。");
  const baseSlots = sources.reduce((total, source) => total + (SPECIAL_SOURCES.has(source) || (source === "wechat_search" && wechatScope === "video") ? 1 : keywords.length), 0);
  if (baseSlots > BASE_QUERY_CAP) throw new Error(`每次最多 ${BASE_QUERY_CAP} 个首屏查询；受限模式按 1 个查询计。请减少平台或关键词。`);
  const extraCalls = (sources.includes("telegram") ? Math.max(0, channels.length - 1) : 0)
    + (sources.includes("toutiao") ? Math.max(0, links.length - 1) : 0)
    + (sources.includes("wechat_search") && wechatScope === "video" ? 2 * shareCount : 0);
  if (baseSlots + extraCalls > MAX_RUN_REQUESTS) throw new Error(`本次需要 ${baseSlots + extraCalls} 次调用，超过每轮 ${MAX_RUN_REQUESTS} 次硬上限。`);
  if (![24, 72, 168, 720].includes(hours)) throw new Error("请选择有效的发布时间窗口。");
  if (conditions) {
    if (conditions.regions.length > 10 || conditions.regions.some(r => !r.trim() || r.length>20) || conditions.roles.length > 12 || conditions.roles.some(r => r.trim().length < 2 || r.trim().length > 20) || conditions.intents.some(i => !HUNT_INTENTS.includes(i))) throw new Error("请检查地区和角色、意图选项。");
    if (conditions.start_at || conditions.end_at) { const start=Date.parse(conditions.start_at ?? ""), end=Date.parse(conditions.end_at ?? ""); if (!Number.isFinite(start) || !Number.isFinite(end) || start>=end || end-start>30*24*3600000) throw new Error("自定义时间须填写有效起止时间，跨度最多30天。"); }
  }
  if (!businessTerms.length || businessTerms.length > 20 || businessTerms.some(term => term.length > 100)) throw new Error("请保留至少一个业务匹配词（最多20个）。");
  if (excludedTerms.length > 20 || excludedTerms.some(term => !term.trim() || term.length > 100)) throw new Error("排除词最多20个，每个1–100字。");
  return {
    name: `${preset.name} · 抓单`, goal: `寻找需要${preset.name}服务的买方公开需求`, mode: "general" as const,
    minimum_budget: 0, frequency: "manual", local_schedule_enabled: false, freshness_hours: hours,
    keywords, sources, locations: [], listener_description: "",
    source_config: { lead_hunt: "true", business: preset.id, freshness_hours: String(hours), ...(conditions ? { hunt_conditions: JSON.stringify(conditions) } : {}), ...(feedUrl.trim() ? { rss_feed_url: feedUrl.trim() } : {}),
      ...(sources.includes("wechat_search") ? { wechat_business_type: wechatScope } : {}),
      ...(sources.includes("wechat_search") && wechatScope === "video" ? { wechat_share_links: String(shareCount) } : {}),
      ...(sources.includes("telegram") ? { telegram_channels: channels.join(",") } : {}),
      ...(sources.includes("toutiao") ? { toutiao_links: links.map(link => link.url).join("\n") } : {}) },
    collection_policy: { ...DEFAULT_COLLECTION_POLICY, required_terms: businessTerms, excluded_terms: excludedTerms, time_basis: "published" as const, include_unknown_dates: false },
  };
}
