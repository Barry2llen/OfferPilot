// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import ToolCallCard from "./tool-call-card";
import ChatMessage from "./chat-message";
import { createChatState, mapChatHistory } from "@/app/lib/chat/adapter";
import i18n from "@/app/lib/i18n";

afterEach(cleanup);

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
