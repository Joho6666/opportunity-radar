/** 个人身份设定（Local Edition）：一次配置，抓单页面自动预填，后端同规则补齐默认值。 */

export type IdentityBusiness = { id: string; name: string; remote_deliverable: boolean };
export type ServiceMode = "remote" | "unspecified" | "regions";
export type LocalIdentity = {
  businesses: IdentityBusiness[];
  target_roles: string[];
  service_mode: ServiceMode;
  regions: string[];
  default_freshness_hours: 24 | 72 | 168 | 720;
  preferred_sources: string[];
  buyer_keywords: string[];
  exclude_words: string[];
  business_match_words: string[];
  quote_style: string;
};

/** 与 backend/app/schemas/identity.py 的 IDENTITY_BUSINESS_PRESETS 同一组 id / 名称。 */
export const IDENTITY_BUSINESS_PRESETS: { id: string; name: string; remote_deliverable: boolean; match_words: string[] }[] = [
  { id: "video", name: "AI 电商视频 / 广告", remote_deliverable: true, match_words: ["电商", "商品", "带货", "广告", "产品视频", "信息流", "视频素材", "亚马逊", "AI视频", "视频生成"] },
  { id: "drama", name: "视频复刻 / AI 短剧", remote_deliverable: true, match_words: ["复刻", "短剧", "视频", "AI剧"] },
  { id: "web", name: "小程序 / 网站轻开发", remote_deliverable: false, match_words: ["小程序", "网站", "网页", "落地页", "官网"] },
  { id: "office", name: "PPT / Word / Excel", remote_deliverable: true, match_words: ["PPT", "Word", "Excel", "演示文稿", "表格", "文档"] },
  { id: "workflow", name: "Skill / 工作流自动化", remote_deliverable: true, match_words: ["自动化", "工作流", "Skill", "Agent", "n8n"] },
];
export const IDENTITY_ROLE_PRESETS = ["电商商家", "品牌方", "实体店", "创业者", "代运营工作室"];
export const IDENTITY_SOURCE_CHOICES: { id: string; name: string }[] = [
  { id: "xiaohongshu", name: "小红书" }, { id: "douyin", name: "抖音" }, { id: "weibo", name: "微博" },
  { id: "zhihu", name: "知乎" }, { id: "bilibili", name: "B站" }, { id: "kuaishou", name: "快手" },
  { id: "lemon8", name: "Lemon8" }, { id: "pipixia", name: "皮皮虾" }, { id: "threads", name: "Threads" },
  { id: "twitter", name: "Twitter" }, { id: "youtube", name: "YouTube" }, { id: "reddit", name: "Reddit" },
  { id: "wechat_search", name: "微信搜索" },
];
export const IDENTITY_FRESHNESS_CHOICES: { value: 24 | 72 | 168 | 720; label: string }[] = [
  { value: 24, label: "24 小时" }, { value: 72, label: "3 天" }, { value: 168, label: "7 天（默认）" }, { value: 720, label: "30 天" },
];

export const DEFAULT_IDENTITY: LocalIdentity = {
  businesses: [], target_roles: [], service_mode: "remote", regions: [], default_freshness_hours: 168,
  preferred_sources: [], buyer_keywords: [], exclude_words: [], business_match_words: [], quote_style: "",
};

const SOURCE_IDS = new Set(IDENTITY_SOURCE_CHOICES.map(item => item.id));

/** 与后端 Pydantic 校验同界；返回中文错误或 null。 */
export function validateIdentity(identity: LocalIdentity): string | null {
  if (identity.businesses.length > 10) return "业务能力最多 10 项。";
  if (identity.businesses.some(item => !item.name.trim() || item.name.length > 40 || !item.id.trim() || item.id.length > 40)) return "业务名称需为 1–40 字。";
  if (identity.target_roles.length > 10 || identity.target_roles.some(role => !role.trim() || role.length > 20)) return "目标客户角色需为 1–20 字，最多 10 个。";
  if (identity.service_mode === "regions" && identity.regions.length === 0) return "指定省市交付时至少填写一个地区。";
  if (identity.regions.length > 10 || identity.regions.some(region => !region.trim() || region.length > 20)) return "服务地区需为 1–20 字，最多 10 个。";
  if (identity.preferred_sources.length > 10 || identity.preferred_sources.some(source => !SOURCE_IDS.has(source))) return "默认平台偏好只能选择当前集成的平台。";
  if (identity.buyer_keywords.length > 10 || identity.buyer_keywords.some(term => !term.trim() || term.length > 100)) return "买方关键词需为 1–100 字，最多 10 个。";
  if (identity.exclude_words.length > 20 || identity.exclude_words.some(term => !term.trim() || term.length > 40)) return "排除词需为 1–40 字，最多 20 个。";
  if (identity.business_match_words.length > 20 || identity.business_match_words.some(term => !term.trim() || term.length > 100)) return "业务匹配词需为 1–100 字，最多 20 个。";
  if (identity.quote_style.length > 500) return "报价/交付风格偏好最多 500 字。";
  return null;
}

export type RadarPrefill = {
  presetId?: string;
  keywords: string[];
  businessTerms: string[];
  excludes: string[];
  hours?: number;
  sources: string[];
  roles: string[];
  regions: string[];
  match_mode: "local" | "remote";
};

export function identityToRadarPrefill(identity: LocalIdentity | null, availableSources: string[]): RadarPrefill {
  if (!identity) return { presetId: undefined, keywords: [], businessTerms: [], excludes: [], hours: undefined, sources: [], roles: [], regions: [], match_mode: "remote" };
  const presetId = identity.businesses.find(business => IDENTITY_BUSINESS_PRESETS.some(preset => preset.id === business.id))?.id;
  const regions = identity.service_mode === "regions" ? identity.regions.slice(0, 10) : [];
  const regionBound = regions.length > 0 && identity.businesses.some(business => !business.remote_deliverable);
  return {
    presetId,
    keywords: [...new Set(identity.buyer_keywords.map(term => term.trim()).filter(Boolean))].slice(0, 3),
    businessTerms: identity.business_match_words.slice(0, 20),
    excludes: identity.exclude_words.slice(0, 20),
    hours: identity.default_freshness_hours,
    sources: identity.preferred_sources.filter(source => availableSources.includes(source)),
    roles: identity.target_roles.filter(role => IDENTITY_ROLE_PRESETS.includes(role)),
    regions,
    match_mode: regionBound ? "local" : "remote",
  };
}
