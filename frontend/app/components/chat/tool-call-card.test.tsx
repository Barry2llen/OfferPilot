// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import ToolCallCard from "./tool-call-card";
import ChatMessage from "./chat-message";
import { createChatState, mapChatHistory } from "@/app/lib/chat/adapter";
import i18n from "@/app/lib/i18n";

afterEach(cleanup);

describe("query answer history", () => {
  it("renders a free-text-only answer and its separate note", async () => {
    await i18n.changeLanguage("en-US");
    render(<ToolCallCard defaultExpanded entry={{
      name: "query", status: "success", toolCallId: "free-text",
      output: { question: "Choose next steps", selected_options: [], free_text: "Only free text", note: "Separate note" },
    }} />);
    expect(document.body.textContent).toContain("Only free text");
    expect(document.body.textContent).toContain("Separate note");
  });

  it.each(["zh-CN", "en-US"])("renders complete dynamic answers in %s", async (locale) => {
    await i18n.changeLanguage(locale);
    const history = mapChatHistory([{
      role: "tool", type: "tool", name: "query", tool_call_id: "decision",
      content: {
        question: "Which next steps?", selection_mode: "multiple",
        options: [{ id: "a", label: "Revise", description: "Revise first" }, { id: "b", label: "Apply", description: "Apply now" }],
        selected_options: [{ id: "a", label: "Revise" }, { id: "b", label: "Apply" }],
        free_text: "Another decision", note: "Preserve this note",
      },
    }], createChatState());
    render(<MemoryRouter><ChatMessage message={history.state.messages[0]} /></MemoryRouter>);
    fireEvent.click(screen.getByRole("button"));
    const text = document.body.textContent;
    for (const part of ["Which next steps?", "Revise", "Apply", "Another decision", "Preserve this note"]) expect(text).toContain(part);
    expect(text).not.toContain("selected_options");
  });

  it.each(["firstChoice", "secondChoice", "thirdChoice", "other"])("keeps legacy %s records readable", async (choice) => {
    await i18n.changeLanguage("en-US");
    render(<ToolCallCard defaultExpanded entry={{
      name: "query", status: "success", toolCallId: "legacy",
      output: { question: "Old question", firstChoice: "First", secondChoice: "Second", thirdChoice: "Third", choice, note: "Old note" },
    }} />);
    expect(document.body.textContent).toContain("Old question");
    expect(document.body.textContent).toContain("Old note");
    if (choice !== "other") expect(document.body.textContent).toContain({ firstChoice: "First", secondChoice: "Second", thirdChoice: "Third" }[choice]);
  });
});

describe("analysis tool card", () => {
  it("shows a result link before expanding and renders current retry progress", async () => {
    await i18n.changeLanguage("zh-CN");
    render(<MemoryRouter><ToolCallCard entry={{
      name: "analyze_resume", toolCallId: "call", status: "running",
      analysis: { resourceType: "resume", resourceId: 3, status: "processing", progress: 0.5,
        message: "正在提取事实", modelError: "正在重试", error: null },
    }} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /查看分析详情/ }).getAttribute("href")).toBe("/resumes/3");
    expect(screen.queryByRole("progressbar")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /简历分析/ }));
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("50");
    expect(screen.getByText("正在重试")).toBeTruthy();
  });

  it("retains the failed JD link in English", async () => {
    await i18n.changeLanguage("en-US");
    const history = mapChatHistory([{
      role: "tool", type: "tool", name: "analyze_job_description", status: "error",
      content: { resource_type: "job_description", resource_id: 8, status: "failed", error: "Analysis was cancelled." },
    }], createChatState());
    render(<MemoryRouter><ChatMessage message={history.state.messages[0]} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /Open analysis details/ }).getAttribute("href")).toBe("/job-descriptions/8");
    expect(screen.getByText("Analysis was cancelled.")).toBeTruthy();
    expect(document.body.textContent).not.toContain("resource_type");
  });
});
