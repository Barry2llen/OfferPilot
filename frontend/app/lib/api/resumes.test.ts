import { describe, expect, it } from "vitest";
import i18n from "@/app/lib/i18n";
import { resumeMediaLabel } from "./resumes";

describe("resumeMediaLabel", () => {
  it("never renders long MIME types verbatim", () => {
    expect(
      resumeMediaLabel(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "Resume.docx",
      ),
    ).toBe("DOCX");
    expect(
      resumeMediaLabel(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        null,
      ),
    ).toBe("DOCX");
    expect(resumeMediaLabel("application/x-some-very-long-vendor-type", null)).toBe(
      i18n.t("common.unknown"),
    );
  });

  it("falls back to the file extension", () => {
    expect(resumeMediaLabel(null, "resume.pdf")).toBe("PDF");
    expect(resumeMediaLabel("application/octet-stream", "cv.rtf")).toBe("RTF");
    expect(resumeMediaLabel("image/png", "shot.png")).toBe(i18n.t("attachments.image"));
  });
});
