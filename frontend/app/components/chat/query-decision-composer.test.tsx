// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import QueryDecisionComposer from "./query-decision-composer";
import ChatRunPanel from "./chat-run-panel";
import type { PendingQueryInput } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";

function question(count = 4, selection_mode: "single" | "multiple" = "single"): PendingQueryInput {
  return {
    type: "query", request_id: "q", run_id: "r", thread_id: "t", tool_call_id: "call",
    question: "How should we continue?", selection_mode,
    options: Array.from({ length: count }, (_, i) => ({
      id: String(i), label: `Option ${i}`, description: `Description ${i}`,
    })),
  };
}

beforeEach(async () => { await i18n.changeLanguage("en-US"); });
afterEach(cleanup);

it.each([2, 4, 6])("renders and submits %i options in either selection mode", (count) => {
  for (const mode of ["single", "multiple"] as const) {
    const onAnswer = vi.fn();
    render(<QueryDecisionComposer input={question(count, mode)} onAnswer={onAnswer} />);
    const controls = screen.getAllByRole(mode === "single" ? "radio" : "checkbox");
    expect(controls).toHaveLength(count);
    if (mode === "single") fireEvent.click(controls[count - 1]);
    else controls.forEach((control) => fireEvent.click(control));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(onAnswer).toHaveBeenCalledWith({
      selected_option_ids: mode === "single" ? [String(count - 1)] : controls.map((_, i) => String(i)),
      free_text: null, note: null,
    });
    cleanup();
  }
});

it("keeps single selection and free text mutually exclusive, with a separate note", () => {
  const onAnswer = vi.fn();
  render(<QueryDecisionComposer input={question()} onAnswer={onAnswer} />);
  const radios = screen.getAllByRole("radio") as HTMLInputElement[];
  const freeText = screen.getByRole("textbox", { name: "Other answer" });
  const note = screen.getByRole("textbox", { name: "Additional note (optional)" });
  fireEvent.click(radios[0]);
  fireEvent.click(radios[2]);
  expect(radios.map((radio) => radio.checked)).toEqual([false, false, true, false]);
  fireEvent.change(note, { target: { value: " context " } });
  fireEvent.change(freeText, { target: { value: " custom " } });
  expect(radios.every((radio) => !radio.checked)).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  expect(onAnswer).toHaveBeenLastCalledWith({ selected_option_ids: [], free_text: "custom", note: "context" });
  fireEvent.click(radios[1]);
  expect((freeText as HTMLTextAreaElement).value).toBe("");
  fireEvent.keyDown(note, { key: "Enter" });
  expect(onAnswer).toHaveBeenLastCalledWith({ selected_option_ids: ["1"], free_text: null, note: "context" });
});

it("toggles multiple options and submits them in question order alongside free text", () => {
  const onAnswer = vi.fn();
  render(<QueryDecisionComposer input={question(4, "multiple")} onAnswer={onAnswer} />);
  const controls = screen.getAllByRole("checkbox");
  [3, 1, 2, 1].forEach((i) => fireEvent.click(controls[i]));
  fireEvent.change(screen.getByRole("textbox", { name: "Other answer" }), { target: { value: "Custom answer" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Additional note (optional)" }), { target: { value: "A note" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  expect(onAnswer).toHaveBeenCalledWith({ selected_option_ids: ["2", "3"], free_text: "Custom answer", note: "A note" });
});

it.each(["single", "multiple"] as const)("rejects blank and note-only answers in %s mode", (mode) => {
  const onAnswer = vi.fn();
  render(<QueryDecisionComposer input={question(2, mode)} onAnswer={onAnswer} />);
  const button = screen.getByRole("button", { name: "Submit" }) as HTMLButtonElement;
  fireEvent.change(screen.getByRole("textbox", { name: "Additional note (optional)" }), { target: { value: "Only a note" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Other answer" }), { target: { value: "  \n " } });
  fireEvent.click(button);
  expect(button.disabled).toBe(true);
  expect(onAnswer).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole("textbox", { name: "Other answer" }), { target: { value: "Answer" } });
  expect(button.disabled).toBe(false);
  fireEvent.click(button);
  expect(onAnswer).toHaveBeenCalledWith({ selected_option_ids: [], free_text: "Answer", note: "Only a note" });
});

it("retains the draft for the same request and resets for a new request", () => {
  const input = question();
  const { rerender } = render(<QueryDecisionComposer input={input} onAnswer={() => {}} />);
  fireEvent.click(screen.getAllByRole("radio")[1]);
  fireEvent.change(screen.getByRole("textbox", { name: "Additional note (optional)" }), { target: { value: "Draft note" } });
  rerender(<QueryDecisionComposer input={{ ...input }} onAnswer={() => {}} />);
  expect((screen.getAllByRole("radio")[1] as HTMLInputElement).checked).toBe(true);
  rerender(<QueryDecisionComposer input={{ ...input, request_id: "next" }} onAnswer={() => {}} />);
  expect((screen.getAllByRole("radio")[1] as HTMLInputElement).checked).toBe(false);
  expect((screen.getByRole("textbox", { name: "Additional note (optional)" }) as HTMLTextAreaElement).value).toBe("");
});

it("preserves the answer after a failed submission and enables retry", async () => {
  const onAnswer = vi.fn().mockRejectedValueOnce(new Error("Try again")).mockResolvedValueOnce(undefined);
  render(<ChatRunPanel runs={[]} inputs={[question(2, "multiple")]} connectionState="connected"
    onAnswer={onAnswer} onCancel={vi.fn()} onCancelQueued={vi.fn()} />);
  fireEvent.click(screen.getAllByRole("checkbox")[1]);
  fireEvent.change(screen.getByRole("textbox", { name: "Other answer" }), { target: { value: "Custom" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  await waitFor(() => expect((screen.getByRole("button", { name: "Submit" }) as HTMLButtonElement).disabled).toBe(false));
  expect((screen.getAllByRole("checkbox")[1] as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole("textbox", { name: "Other answer" }) as HTMLTextAreaElement).value).toBe("Custom");
  fireEvent.click(screen.getByRole("button", { name: "Submit" }));
  await waitFor(() => expect(onAnswer).toHaveBeenCalledTimes(2));
  expect(onAnswer.mock.calls[1]).toEqual(onAnswer.mock.calls[0]);
});

it("localizes labels and mode hints while preserving the question and choices", async () => {
  await i18n.changeLanguage("zh-CN");
  render(<QueryDecisionComposer input={question(2, "multiple")} onAnswer={() => {}} />);
  expect(screen.getByText(/多选：/)).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "手填答案" })).toBeTruthy();
  expect(screen.getByRole("textbox", { name: "补充说明（可选）" })).toBeTruthy();
  expect(screen.getByText("How should we continue?")).toBeTruthy();
  expect(screen.getByText("Option 1")).toBeTruthy();
});
