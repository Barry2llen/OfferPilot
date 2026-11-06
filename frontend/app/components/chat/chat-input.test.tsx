// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import ChatInput from "./chat-input";
import { ToastProvider } from "@/app/components/ui/toast";
import i18n from "@/app/lib/i18n";

afterEach(cleanup);

it("keeps the new draft editable and preserves it after the previous submission is accepted", async () => {
  await i18n.changeLanguage("en-US");
  let accept = () => {};
  const onSend = vi.fn((_payload, accepted: () => void) => {
    accept = accepted;
  });
  const { rerender } = render(
    <ToastProvider>
      <ChatInput
        onSend={onSend}
        onStop={() => {}}
        isStreaming={false}
        disabled={false}
      />
    </ToastProvider>,
  );
  const input = screen.getByRole("textbox");
  const placeholder = input.getAttribute("placeholder");
  fireEvent.change(input, { target: { value: "first" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  rerender(
    <ToastProvider>
      <ChatInput
        onSend={onSend}
        onStop={() => {}}
        isStreaming={false}
        disabled={false}
        submitting
      />
    </ToastProvider>,
  );
  expect(input.getAttribute("placeholder")).toBe(placeholder);
  expect((input as HTMLTextAreaElement).disabled).toBe(false);
  fireEvent.change(input, { target: { value: "next draft" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(onSend).toHaveBeenCalledTimes(1);
  act(() => accept());
  expect((input as HTMLTextAreaElement).value).toBe("next draft");
});

it("removes only sent attachments when a new attachment is added before acceptance", async () => {
  await i18n.changeLanguage("en-US");
  let accept = () => {};
  const onSend = vi.fn((_payload, accepted: () => void) => {
    accept = accepted;
  });
  const { container } = render(
    <ToastProvider>
      <ChatInput
        onSend={onSend}
        onStop={() => {}}
        isStreaming={false}
        disabled={false}
      />
    </ToastProvider>,
  );
  const fileInput = container.querySelector('input[type="file"]')!;
  fireEvent.change(fileInput, {
    target: {
      files: [new File(["first"], "first.txt", { type: "text/plain" })],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  fireEvent.change(fileInput, {
    target: { files: [new File(["next"], "next.txt", { type: "text/plain" })] },
  });
  act(() => accept());
  expect(screen.queryByText("first.txt")).toBeNull();
  expect(screen.getByText("next.txt")).toBeTruthy();
});


it("does not send while an IME composition is being confirmed", async () => {
  await i18n.changeLanguage("en-US");
  const onSend = vi.fn();
  render(<ToastProvider><ChatInput onSend={onSend} onStop={() => {}} isStreaming={false} disabled={false} /></ToastProvider>);
  const input = screen.getByRole("textbox");
  fireEvent.change(input, { target: { value: "优化项目经历" } });
  fireEvent.keyDown(input, { key: "Enter", isComposing: true });
  fireEvent.keyDown(input, { key: "Enter", keyCode: 229 });
  expect(onSend).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter" });
  expect(onSend).toHaveBeenCalledTimes(1);
});

it("uses Enter for a new line on mobile and a modifier to send", async () => {
  await i18n.changeLanguage("en-US");
  const original = window.matchMedia;
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === "(max-width: 767px)", media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  }));
  try {
    const onSend = vi.fn();
    render(<ToastProvider><ChatInput onSend={onSend} onStop={() => {}} isStreaming={false} disabled={false} /></ToastProvider>);
    const input = screen.getByRole("textbox");
    fireEvent.change(input, { target: { value: "next step" } });
    expect(fireEvent.keyDown(input, { key: "Enter" })).toBe(true);
    expect(onSend).not.toHaveBeenCalled();
    fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });
    expect(onSend).toHaveBeenCalledTimes(1);
  } finally { cleanup(); window.matchMedia = original; }
});

it("renders trailing controls inside the composer and offers stop and enqueue while streaming", async () => {
  await i18n.changeLanguage("en-US");
  const onStop = vi.fn();
  render(
    <ToastProvider>
      <ChatInput
        onSend={() => {}}
        onStop={onStop}
        isStreaming
        disabled={false}
        trailing={<button type="button">Thinking picker</button>}
      />
    </ToastProvider>,
  );
  expect(screen.getByRole("button", { name: "Thinking picker" })).toBeTruthy();
  expect(screen.getByRole("button", { name: i18n.t("chatRuns.enqueue") })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: i18n.t("chatRuns.stopCurrent") }));
  expect(onStop).toHaveBeenCalledTimes(1);
});
