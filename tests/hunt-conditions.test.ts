import { expect, it } from "vitest";
import { BUSINESS_PRESETS, buildLeadRadar, previewHuntQueries, readHuntConditions, describeHuntConditions, shanghaiToUtc, utcToShanghaiInput } from "../lib/lead-hunt";
it("保存3天、控制变量JSON并保持地区对照与六调用上限", () => {
 const c = { regions: ["深圳"], roles: ["电商商家"], intents: ["长期合作"], match_mode: "remote" as const };
 const r = buildLeadRadar(BUSINESS_PRESETS[0], ["xiaohongshu","douyin"], "视频外包，找人做视频，视频制作", 72, "", undefined, c);
 expect(JSON.parse(r.source_config.hunt_conditions!)).toEqual(c);
 expect(previewHuntQueries(r.keywords,r.sources,c)).toEqual(["视频外包","找人做视频","深圳 视频外包"]);
 expect(shanghaiToUtc("2026-10-16T08:30")).toBe("2026-10-16T00:30:00.000Z");
});
it("自定义时间和角色地区可从保存JSON恢复为上海时间编辑值", () => {
 const c={ regions:["深圳","佛山"], roles:["品牌方"], intents:["咨询方案"], match_mode:"local" as const, start_at:shanghaiToUtc("2026-10-10T08:00"),end_at:shanghaiToUtc("2026-10-16T20:00") };
 const r=buildLeadRadar(BUSINESS_PRESETS[0],["xiaohongshu"],"视频外包",720,"",undefined,c);
 const saved=JSON.parse(JSON.stringify(r));
 expect(readHuntConditions(saved.source_config)).toEqual(c);
 expect(utcToShanghaiInput(readHuntConditions(saved.source_config).start_at)).toBe("2026-10-10T08:00");
 expect(describeHuntConditions(saved.source_config)).toContain("深圳 / 佛山 · 品牌方 · 咨询方案 · 严格本地");
 expect(describeHuntConditions({})).toContain("旧版配置");
});
it("条件不突破关键词请求上限，自定义反向区间拒绝保存", () => {
 const c={regions:["广州"],roles:[],intents:[],match_mode:"keep_unknown" as const};
 const sources=["xiaohongshu","douyin","weibo","zhihu"];
 expect(previewHuntQueries(["视频外包"],sources,c)).toEqual(["视频外包"]);
 expect(() => buildLeadRadar(BUSINESS_PRESETS[0],sources,"视频外包，视频制作",72,"",undefined,c)).toThrow();
 expect(() => buildLeadRadar(BUSINESS_PRESETS[0],["xiaohongshu"],"视频外包",720,"",undefined,{...c,start_at:"2026-10-17T00:00:00Z",end_at:"2026-10-01T00:00:00Z"})).toThrow("自定义时间");
});
