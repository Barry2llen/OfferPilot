// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef, type RefObject } from "react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ToastProvider } from "@/app/components/ui/toast";
import type { ChatRun, PendingQueryInput } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";
import ChatArea from "./chat-area";
import ChatRunPanel from "./chat-run-panel";

const failedRun: ChatRun = {
  run_id: "run", thread_id: "thread", status: "failed", sequence: 1,
  prompt: "First message", selection_id: 1, message_id: "message",
  detail: "Model is unavailable", pending_inputs: [], last_event_id: 1,
  requires_image_input: false, resolved_attachments: [],
};

const pendingInput: PendingQueryInput = {
  type: "query", request_id: "question", run_id: "run", thread_id: "thread",
  tool_call_id: "tool", question: "Which role?", selection_mode: "single",
  options: [
    { id: "first", label: "First role", description: "Review the first role" },
    { id: "second", label: "Second role", description: "Review the second role" },
  ],
};

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true, value: vi.fn(),
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
afterAll(() => {
  Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
});

function view({ historyLoading = false, pending = false, pendingInputRef }: {
  historyLoading?: boolean;
  pending?: boolean;
  pendingInputRef?: RefObject<HTMLDivElement | null>;
} = {}) {
  return (
    <MemoryRouter>
      <ToastProvider>
        <ChatArea messages={[]} liveMessages={[]} isStreaming={pending}
          activityKey={pending ? pendingInput.request_id : undefined} pendingInputRef={pendingInputRef}
          historyLoading={historyLoading} streamError={pending ? null : "Submission failed"}
          contextCompactionStatus="idle" modelContextWindowWarning={null}
          threadModelMismatchMessage={null} hasNoModel={false} onPrompt={() => {}}>
          <ChatRunPanel runs={pending ? [] : [failedRun]} inputs={pending ? [pendingInput] : []}
            pendingInputRef={pendingInputRef} connectionState="reconnecting" onAnswer={async () => {}}
            onCancel={async () => {}} onCancelQueued={async () => {}} />
        </ChatArea>
      </ToastProvider>
    </MemoryRouter>
  );
}

describe.each(["en-US", "zh-CN"])("chat status visibility in %s", (locale) => {
  beforeEach(async () => { await i18n.changeLanguage(locale); });

  it("shows failed runs, connection state, and submission errors with an empty history", () => {
    render(view());
    expect(screen.getByText(i18n.t("welcome.greeting"))).toBeTruthy();
    expect(screen.getByText(i18n.t("chatRuns.reconnecting"))).toBeTruthy();
    expect(screen.getByText(i18n.t("chatRuns.failed", { prompt: failedRun.prompt }))).toBeTruthy();
    expect(screen.getByText(failedRun.detail!)).toBeTruthy();
    expect(screen.getByText("Submission failed")).toBeTruthy();
  });

  it("keeps a pending answer draft mounted while history reloads", () => {
    const { rerender } = render(view({ pending: true }));
    const answer = screen.getByLabelText(i18n.t("chat.queryFreeText")) as HTMLTextAreaElement;
    fireEvent.change(answer, { target: { value: "My draft" } });

    rerender(view({ pending: true, historyLoading: true }));
    expect(screen.getByLabelText(i18n.t("chat.queryFreeText"))).toBe(answer);
    expect(answer.value).toBe("My draft");
    expect(screen.getByText(i18n.t("chatRuns.reconnecting"))).toBeTruthy();

    rerender(view({ pending: true }));
    expect((screen.getByLabelText(i18n.t("chat.queryFreeText")) as HTMLTextAreaElement).value).toBe("My draft");
  });

  it("offers a jump when the start of a pending request is outside the viewport", () => {
    let callback: IntersectionObserverCallback | undefined;
    const observe = vi.fn();
    class Observer {
      constructor(onChange: IntersectionObserverCallback) { callback = onChange; }
      observe = observe;
      disconnect() {}
    }
    vi.stubGlobal("IntersectionObserver", Observer);
    const pendingInputRef = createRef<HTMLDivElement>();
    const { container, rerender } = render(view({ pendingInputRef }));
    const scroll = container.querySelector(".chat-scroll")!;
    Object.defineProperties(scroll, {
      clientHeight: { configurable: true, value: 500 },
      scrollHeight: { configurable: true, value: 1000 },
      scrollTop: { configurable: true, value: 400 },
    });
    fireEvent.scroll(scroll);
    expect(screen.queryByRole("button", { name: i18n.t("chat.viewPendingInput") })).toBeNull();

    rerender(view({ pending: true, pendingInputRef }));
    const target = pendingInputRef.current!;
    const scrollIntoView = vi.spyOn(target, "scrollIntoView");
    expect(callback).toBeDefined();
    // The form itself may still intersect the viewport even when its start does not.
    expect(observe).toHaveBeenCalledWith(target.querySelector("[data-pending-start]"));
    act(() => callback?.([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver));
    fireEvent.click(screen.getByRole("button", { name: i18n.t("chat.viewPendingInput") }));
    expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth", block: "start" });
    expect(document.activeElement).toBe(target);

    act(() => callback?.([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(screen.queryByRole("button", { name: i18n.t("chat.viewPendingInput") })).toBeNull();
  });
});
