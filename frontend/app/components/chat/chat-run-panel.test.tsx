// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/app/components/ui/toast";
import type { InputAnswer, PendingInput, PendingQueryInput } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";
import ChatRunPanel from "./chat-run-panel";

const input: PendingQueryInput = {
  type: "query",
  request_id: "question",
  run_id: "run",
  thread_id: "thread",
  tool_call_id: "tool",
  question: "Which experience should we focus on?",
  selection_mode: "multiple",
  options: [
    { id: "first", label: "First role", description: "Focus on the first role" },
    { id: "second", label: "Second role", description: "Focus on the second role" },
  ],
};

// jsdom has no native dialog API; browser checks cover top-layer visibility.
beforeAll(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value(this: HTMLDialogElement) { this.open = true; } },
    close: { configurable: true, value(this: HTMLDialogElement) { this.open = false; } },
  });
});

beforeEach(() => {
  vi.stubGlobal("matchMedia", vi.fn().mockImplementation((query: string) => ({
    matches: query === "(max-width: 767px)",
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

afterAll(() => {
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});

function openPanel(pendingInput: PendingInput, onAnswer: (input: PendingInput, answer: InputAnswer) => Promise<void>) {
  render(
    <ToastProvider>
      <ChatRunPanel runs={[]} inputs={[pendingInput]} connectionState="connected"
        onAnswer={onAnswer} onCancel={async () => {}} onCancelQueued={async () => {}} />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: i18n.t("appearance.answer") }));
  return screen.getByRole("dialog") as HTMLDialogElement;
}

describe.each(["en-US", "zh-CN"])("mobile answer failures in %s", (locale) => {
  beforeEach(async () => { await i18n.changeLanguage(locale); });

  it("reports the error, keeps the answer draft and allows a successful retry", async () => {
    const message = "Review service unavailable: answer was not saved";
    const onAnswer = vi.fn<(input: PendingInput, answer: InputAnswer) => Promise<void>>()
      .mockRejectedValueOnce(new Error(message))
      .mockResolvedValueOnce(undefined);
    const dialog = openPanel(input, onAnswer);
    const choice = within(dialog).getAllByRole("checkbox")[0] as HTMLInputElement;
    const freeText = within(dialog).getByLabelText(i18n.t("chat.queryFreeText")) as HTMLTextAreaElement;
    const note = within(dialog).getByLabelText(i18n.t("chat.queryNote")) as HTMLTextAreaElement;
    fireEvent.click(choice);
    fireEvent.change(freeText, { target: { value: "Also review the portfolio" } });
    fireEvent.change(note, { target: { value: "Keep these details" } });
    const submit = within(dialog).getByRole("button", { name: i18n.t("chat.submit") }) as HTMLButtonElement;
    fireEvent.click(submit);

    expect(await screen.findByText(message)).toBeTruthy();
    expect(dialog.open).toBe(true);
    expect(choice.checked).toBe(true);
    expect(freeText.value).toBe("Also review the portfolio");
    expect(note.value).toBe("Keep these details");
    expect(submit.disabled).toBe(false);

    fireEvent.click(submit);
    await waitFor(() => expect(dialog.open).toBe(false));
    expect(onAnswer).toHaveBeenCalledTimes(2);
    expect(onAnswer).toHaveBeenNthCalledWith(2, input, {
      selected_option_ids: ["first"],
      free_text: "Also review the portfolio",
      note: "Keep these details",
    });
  });

  it("uses the active locale when retrying an error input fails without a message", async () => {
    const onAnswer = vi.fn<(input: PendingInput, answer: InputAnswer) => Promise<void>>()
      .mockRejectedValueOnce(null);
    const errorInput: PendingInput = { ...input, type: "error", message: "Upstream interrupted" };
    const dialog = openPanel(errorInput, onAnswer);
    const retry = within(dialog).getByRole("button", { name: i18n.t("chat.retry") }) as HTMLButtonElement;
    fireEvent.click(retry);

    expect(await screen.findByText(i18n.t("errors.submitFailed"))).toBeTruthy();
    expect(dialog.open).toBe(true);
    expect(retry.disabled).toBe(false);
    expect(onAnswer).toHaveBeenCalledWith(errorInput, { type: "retry" });
  });
});
