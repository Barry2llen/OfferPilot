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
