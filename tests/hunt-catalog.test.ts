import { describe, expect, it } from "vitest";
import { isHuntSourceSelectable } from "../lib/lead-hunt";

describe("platform selection is not availability", () => {
  it("allows saving integrated but unconfigured sources and disables pending catalogs", () => {
    expect(isHuntSourceSelectable({ id: "reddit", name: "Reddit", available: false, status: "未配置", detail: "契约", selectable: true })).toBe(true);
    expect(isHuntSourceSelectable({ id: "youtube", name: "YouTube", available: false, status: "待接入", detail: "未知返回结构", selectable: false })).toBe(false);
  });
});
