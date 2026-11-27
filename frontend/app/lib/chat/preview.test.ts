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

  it("removes table separator rows while preserving hyphens inside text", () => {
    expect(plainPreview("foo---bar\nName | Role\n:--- | ---:\nLee | Engineer")).toBe(
      "foo---bar Name Role Lee Engineer",
    );
  });

  it("bounds Markdown cleanup to the start of a long preview", () => {
    const blank = " ".repeat(32_000);
    expect(plainPreview(`${blank}First line\n${blank}Past the preview`)).toBe("First line");
  });

  it("returns an empty string for missing previews", () => {
    expect(plainPreview(null)).toBe("");
    expect(plainPreview("   ")).toBe("");
  });
});
