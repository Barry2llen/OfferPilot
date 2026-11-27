import { afterAll, describe, expect, it } from "vitest";
import i18n from "@/app/lib/i18n";
import { analysisLabel, humanizeToken } from "./analysis-labels";

describe("analysisLabel", () => {
  afterAll(async () => {
    await i18n.changeLanguage("zh-CN");
  });

  it("localizes known fact, block and importance values", async () => {
    await i18n.changeLanguage("zh-CN");
    expect(analysisLabel("factType", "achievement")).toBe("成果");
    expect(analysisLabel("blockType", "must_have")).toBe("必备要求");
    expect(analysisLabel("importance", "nice_to_have")).toBe("加分");

    await i18n.changeLanguage("en-US");
    expect(analysisLabel("factType", "work_experience")).toBe("Work experience");
    expect(analysisLabel("importance", "unknown")).toBe("Unrated");
  });

  it("keeps unknown model categories readable", async () => {
    await i18n.changeLanguage("en-US");
    expect(analysisLabel("factType", "distributed_system_experience")).toBe(
      "Distributed system experience",
    );
    expect(humanizeToken("  team-lead_role ")).toBe("Team lead role");
  });
});

describe("English pluralization", () => {
  it("uses singular nouns for a count of one and formats numbers", async () => {
    await i18n.changeLanguage("en-US");
    expect(i18n.t("settings.providerCount", { count: 1 })).toBe("1 provider");
    expect(i18n.t("settings.modelCount", { count: 1200 })).toBe("1,200 models");
    expect(i18n.t("resume.shortFactCount", { count: 1 })).toBe("1 fact");
    expect(i18n.t("resume.stats", { count: 1, total: "1", parsed: "1" })).toBe(
      "1 resume, 1 parsed",
    );
  });
});
