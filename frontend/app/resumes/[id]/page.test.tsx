// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import { ToastProvider } from "@/app/components/ui/toast";
import { resumesApi } from "@/app/lib/api/resumes";
import type { ResumeDetail } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";
import ResumeDetailPage from "./page";

vi.mock("@/app/lib/context/app-context", () => ({
  useAppContext: () => ({ state: { analysisEventVersions: { resume: 0 }, analysisTasks: {} } }),
}));
vi.mock("@/app/components/resumes/resume-uploader", () => ({
  default: () => <div data-testid="replacement-uploader">Replacement uploader</div>,
}));

const resume: ResumeDetail = {
  id: 42, file_path: "resume.pdf", upload_time: "2026-11-16T00:00:00Z",
  original_filename: "resume.pdf", media_type: "application/pdf", has_file: true,
  preview_url: "/resumes/42/file", parse_status: "parsed", parse_error: null,
  parsed_at: null, summary: "Summary", section_count: 0, fact_count: 0,
  raw_text: "Resume text", sections: [],
};

beforeEach(async () => { await i18n.changeLanguage("en-US"); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function renderPage(detail: ResumeDetail) {
  vi.spyOn(resumesApi, "get").mockResolvedValue(detail);
  const view = render(
    <MemoryRouter initialEntries={["/resumes/42"]}>
      <ToastProvider><Routes><Route path="/resumes/:id" element={<ResumeDetailPage />} /></Routes></ToastProvider>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: "resume" });
  return view;
}

describe("resume source preview", () => {
  it.each([
    { mediaType: "application/pdf", filename: "resume.pdf", selector: "iframe" },
    { mediaType: "image/png", filename: "resume.png", selector: "img" },
  ])("loads the $mediaType original only while it is shown", async ({ mediaType, filename, selector }) => {
    const { container } = await renderPage({ ...resume, media_type: mediaType, original_filename: filename });
    expect(container.querySelector(selector)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: i18n.t("resume.showOriginal") }));
    expect(container.querySelector(selector)?.getAttribute("src")).toBe("/resumes/42/file");

    fireEvent.click(screen.getByRole("button", { name: i18n.t("resume.hideOriginal") }));
    expect(container.querySelector(selector)).toBeNull();
  });

  it("keeps the replacement uploader mounted if the source pane is hidden", async () => {
    await renderPage(resume);
    fireEvent.click(screen.getByRole("button", { name: i18n.t("resume.replace") }));
    const uploader = screen.getByTestId("replacement-uploader");
    fireEvent.click(screen.getByRole("button", { name: i18n.t("resume.hideOriginal") }));
    expect(screen.getByTestId("replacement-uploader")).toBe(uploader);
  });
});
