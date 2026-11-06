import { describe, expect, it } from "vitest";
import { plainPreview } from "./preview";

describe("plainPreview", () => {
  it("removes headings, rules and table pipes from model replies", () => {
    expect(
      plainPreview("--- ## ✅ 三个工具测试完成！总结如下 | 工具 | 功能 |\n|---|---|"),
    ).toBe("✅ 三个工具测试完成！总结如下 工具 功能");
  });

  it("keeps link text, inline code and code block content", () => {
    expect(
      plainPreview("See [docs](https://example.com) and `npm i`\n```bash\npnpm build\n```"),
    ).toBe("See docs and npm i pnpm build");
  });

  it("strips list and emphasis markers", () => {
    expect(plainPreview("1. **Fix** layout\n- ~~old~~ new")).toBe("Fix layout old new");
  });

  it("returns an empty string for missing previews", () => {
    expect(plainPreview(null)).toBe("");
    expect(plainPreview("   ")).toBe("");
  });
});
