import { describe, expect, it } from "vitest";
import { REGION_TREE, addRegion, allRegionNames, regionLabel, regionNodes } from "../lib/region-tree";

describe("region tree", () => {
  it("keeps every place name unique and within the stored limit", () => {
    const names = allRegionNames();
    expect(new Set(names).size).toBe(names.length);
    expect(names.every(name => name.length >= 1 && name.length <= 20)).toBe(true);
    expect(REGION_TREE.map(node => node.name)).toContain("美国");
    expect(REGION_TREE.map(node => node.name)).toContain("中国");
  });

  it("commits the deepest selected level and shows the full path", () => {
    expect(regionNodes(["中国"]).some(node => node.name === "广东")).toBe(true);
    expect(regionNodes(["中国", "广东"]).map(node => node.name)).toContain("深圳");
    expect(regionNodes(["美国", "加利福尼亚"]).map(node => node.name)).toEqual(["洛杉矶", "旧金山", "圣何塞"]);
    expect(regionNodes(["新加坡"])).toEqual([]);
    const added = addRegion([], ["美国", "加利福尼亚", "洛杉矶"]);
    expect(added).toEqual({ regions: ["洛杉矶"] });
    expect(regionLabel("洛杉矶")).toBe("美国 / 加利福尼亚 / 洛杉矶");
    expect(regionLabel("美国")).toBe("美国");
    expect(addRegion(["洛杉矶"], ["美国", "加利福尼亚", "洛杉矶"]).error).toBe("这个地区已经添加");
    expect(addRegion([], []).error).toBe("先选择国家或地区");
    expect(addRegion(Array.from({ length: 10 }, (_, index) => `地区${index}`), ["日本"]).error).toBe("最多 10 个地区");
    expect(regionLabel("清远")).toBe("清远");
  });
});
