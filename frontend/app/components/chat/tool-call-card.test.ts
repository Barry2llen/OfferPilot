import { describe, expect, it } from "vitest";
import { analysisDetailPath } from "@/app/lib/analysis-events/links";

describe("analysis tool card links", () => {
  it("links resume and job description results to their detail pages", () => {
    expect(
      analysisDetailPath("resume", 3),
    ).toBe("/resumes/3");
    expect(
      analysisDetailPath("job_description", 8),
    ).toBe("/job-descriptions/8");
  });
});
