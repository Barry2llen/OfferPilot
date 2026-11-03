// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ModelProviderResponse, ModelSelectionResponse, ThinkingSettings } from "@/app/lib/api/types";
import i18n from "@/app/lib/i18n";
import SelectionForm from "./selection-form";

const providers: ModelProviderResponse[] = [
  "OpenAI", "OpenAI Compatible", "Google", "DeepSeek", "Anthropic",
].map((provider) => ({ provider, name: provider, base_url: null, has_api_key: false }));

function renderForm(provider: string, initial?: ModelSelectionResponse) {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const { container } = render(
    <SelectionForm providers={providers} defaultProviderName={provider} initial={initial}
      onSubmit={onSubmit} onCancel={() => {}} submitting={false} />,
  );
  if (!initial) {
    fireEvent.change(screen.getByPlaceholderText(i18n.t("settings.modelNamePlaceholder")), {
      target: { value: "model" },
    });
  }
  return {
    onSubmit,
    form: container.querySelector("form")!,
    async submit() {
      const previousCalls = onSubmit.mock.calls.length;
      fireEvent.click(screen.getByRole("button", {
        name: i18n.t(initial ? "settings.save" : "common.create"),
      }));
      await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(previousCalls + 1));
      return onSubmit.mock.lastCall![0];
    },
  };
}

function selection(provider: string, thinking?: ThinkingSettings | null): ModelSelectionResponse {
  return {
    id: 1,
    provider: providers.find((item) => item.provider === provider)!,
    model_name: "model",
    supports_image_input: false,
    context_window_tokens: 128000,
    api_mode: "auto",
    thinking,
    extra_params: {},
  };
}

afterEach(cleanup);

describe.each(["en-US", "zh-CN"])("nullable thinking settings in %s", (locale) => {
  beforeEach(async () => { await i18n.changeLanguage(locale); });

  it.each(providers)("creates $provider models with no thinking settings by default", async ({ provider }) => {
    const { submit } = renderForm(provider);
    expect((await submit()).thinking).toBeNull();
  });

  const emptySettings: (ThinkingSettings | null | undefined)[] = [
    null, undefined, { type: "adaptive", value: null },
  ];
  it.each(emptySettings)("saves an existing empty setting %j as null", async (thinking) => {
    const { submit } = renderForm("Anthropic", selection("Anthropic", thinking));
    expect((await submit()).thinking).toBeNull();
  });

  it("saves a selected effort and clears it when returning to the provider default", async () => {
    const { submit } = renderForm("OpenAI");
    const input = screen.getByRole("combobox", { name: i18n.t("settings.thinkingValue") });
    fireEvent.change(input, { target: { value: "high" } });
    expect((await submit()).thinking).toEqual({ type: "effort", value: "high" });
    fireEvent.change(input, { target: { value: "" } });
    expect((await submit()).thinking).toBeNull();
  });

  it.each([
    { provider: "OpenAI", type: "effort" as const, value: "none" },
    { provider: "DeepSeek", type: "deepseek" as const, value: "disabled" },
  ])("preserves the explicit $value setting for $provider", async ({ provider, type, value }) => {
    const thinking = { type, value };
    const { submit } = renderForm(provider, selection(provider, thinking));
    expect((await submit()).thinking).toEqual(thinking);
  });

  it("clears provider-specific thinking and API mode when changing providers", async () => {
    const initial = selection("OpenAI", { type: "effort", value: "high" });
    initial.api_mode = "responses";
    const { submit } = renderForm("OpenAI", initial);
    fireEvent.change(screen.getAllByRole("combobox")[0], { target: { value: "Anthropic" } });
    expect((await submit())).toMatchObject({ provider_name: "Anthropic", api_mode: "auto", thinking: null });
  });

  it("keeps the budget draft visible without requiring max tokens until a budget is entered", async () => {
    const { submit, form } = renderForm("Anthropic");
    fireEvent.change(screen.getByRole("combobox", { name: i18n.t("settings.thinking") }), {
      target: { value: "budget" },
    });
    const budget = screen.getByRole("spinbutton", { name: i18n.t("settings.thinkingBudget") });
    const maxTokens = screen.getByRole("spinbutton", { name: i18n.t("settings.maxTokens") }) as HTMLInputElement;
    expect(maxTokens.required).toBe(false);
    expect(form.checkValidity()).toBe(true);
    expect((await submit()).thinking).toBeNull();
    fireEvent.change(budget, { target: { value: "1024" } });
    expect(maxTokens.required).toBe(true);
    expect(form.checkValidity()).toBe(false);
    fireEvent.change(maxTokens, { target: { value: "4096" } });
    expect(form.checkValidity()).toBe(true);
    expect((await submit()).thinking).toEqual({ type: "budget", value: 1024, max_tokens: 4096 });
  });

  it.each([0, -1, 1024])("preserves the Google budget %s", async (value) => {
    const { submit } = renderForm("Google");
    fireEvent.change(screen.getByRole("combobox", { name: i18n.t("settings.thinking") }), {
      target: { value: "budget" },
    });
    fireEvent.change(screen.getByRole("spinbutton", { name: i18n.t("settings.thinkingBudget") }), {
      target: { value: String(value) },
    });
    expect((await submit()).thinking).toEqual({ type: "budget", value });
  });

  it.each(["Google", "Anthropic"])("clears an existing %s budget", async (provider) => {
    const thinking: ThinkingSettings = { type: "budget", value: 1024 };
    if (provider === "Anthropic") thinking.max_tokens = 4096;
    const { submit, form } = renderForm(provider, selection(provider, thinking));
    fireEvent.change(screen.getByRole("spinbutton", { name: i18n.t("settings.thinkingBudget") }), {
      target: { value: "" },
    });
    if (provider === "Anthropic") {
      const maxTokens = screen.getByRole("spinbutton", { name: i18n.t("settings.maxTokens") }) as HTMLInputElement;
      fireEvent.change(maxTokens, { target: { value: "" } });
      expect(maxTokens.required).toBe(false);
    }
    expect(form.checkValidity()).toBe(true);
    expect((await submit()).thinking).toBeNull();
  });
});
