// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import FormDrawer from "@/app/components/ui/form-drawer";
import type { ModelSelectionResponse } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";
import ModelSelectionPicker from "./model-selection-picker";

const model: ModelSelectionResponse = {
  id: 1, provider: { provider: "OpenAI", name: "Example", base_url: null, has_api_key: true },
  model_name: "model", supports_image_input: false, context_window_tokens: 128000,
};

beforeAll(() => {
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: { configurable: true, value(this: HTMLDialogElement) { this.open = true; } },
    close: { configurable: true, value(this: HTMLDialogElement) { this.open = false; } },
  });
});
afterEach(cleanup);
afterAll(() => {
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
});

describe.each(["en-US", "zh-CN"])("model picker Escape in %s", (locale) => {
  beforeEach(async () => { await i18n.changeLanguage(locale); });

  it("closes the inline menu without dismissing its containing drawer", () => {
    const onClose = vi.fn();
    render(
      <FormDrawer open title="Upload" onClose={onClose}>
        <ModelSelectionPicker models={[model]} loading={false} value={model.id} onChange={() => {}} />
      </FormDrawer>,
    );
    const drawer = screen.getByRole("dialog", { name: "Upload" }) as HTMLDialogElement;
    const trigger = within(drawer).getByRole("button", { name: i18n.t("chat.chooseModel") });
    fireEvent.click(trigger);
    const search = within(drawer).getByRole("textbox", { name: i18n.t("chat.searchModels") });
    search.focus();
    const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
    fireEvent(search, event);

    expect(event.defaultPrevented).toBe(true);
    expect(drawer.open).toBe(true);
    expect(onClose).not.toHaveBeenCalled();
    expect(within(drawer).queryByRole("textbox", { name: i18n.t("chat.searchModels") })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });
});
