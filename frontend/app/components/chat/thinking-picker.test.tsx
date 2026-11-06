// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ModelSelectionResponse, ThinkingSettings } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";
import ThinkingPicker from "./thinking-picker";

afterEach(cleanup);
beforeEach(async () => {
  await i18n.changeLanguage("en-US");
});

function model(provider: string, thinking?: ThinkingSettings | null): ModelSelectionResponse {
  return {
    id: 1,
    provider: { provider, name: provider, base_url: null, has_api_key: true },
    model_name: "model",
    supports_image_input: false,
    context_window_tokens: 128000,
    api_mode: "auto",
    thinking,
    extra_params: {},
  };
}

function choose(label: string) {
  fireEvent.click(screen.getByRole("combobox", { name: i18n.t("chat.thinkingIntensity") }));
  fireEvent.click(screen.getByRole("option", { name: label }));
}

it("sends an explicit value and clears the override when returning to the saved default", () => {
  const onChange = vi.fn();
  const saved = model("OpenAI", { type: "effort", value: "low" });
  const { rerender } = render(<ThinkingPicker model={saved} override={undefined} onChange={onChange} />);
  choose(i18n.t("settings.thinkingValue_high"));
  expect(onChange).toHaveBeenLastCalledWith({ value: "high" });

  rerender(<ThinkingPicker model={saved} override={{ value: "high" }} onChange={onChange} />);
  choose(i18n.t("chat.thinkingDefault", { value: i18n.t("settings.thinkingValue_low") }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});

it("falls back to the provider default thinking type when the selection has none", () => {
  const onChange = vi.fn();
  render(<ThinkingPicker model={model("DeepSeek")} override={undefined} onChange={onChange} />);
  choose(i18n.t("settings.thinkingValue_disabled"));
  expect(onChange).toHaveBeenLastCalledWith({ value: "disabled" });
});

it("renders nothing without a model or for providers without thinking support", () => {
  const { container, rerender } = render(<ThinkingPicker model={undefined} override={undefined} onChange={() => {}} />);
  expect(container.innerHTML).toBe("");
  rerender(<ThinkingPicker model={model("Unknown")} override={undefined} onChange={() => {}} />);
  expect(container.innerHTML).toBe("");
});

it("edits a budget override in a popover", () => {
  const onChange = vi.fn();
  render(<ThinkingPicker model={model("Google", { type: "budget", value: 512 })} override={undefined} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: i18n.t("chat.thinkingIntensity") }));
  fireEvent.change(screen.getByRole("spinbutton", { name: i18n.t("settings.thinkingBudget") }), { target: { value: "2048" } });
  expect(onChange).toHaveBeenLastCalledWith({ value: 2048 });
  fireEvent.click(screen.getByRole("button", { name: new RegExp(i18n.t("chat.thinkingUseDefault")) }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});
