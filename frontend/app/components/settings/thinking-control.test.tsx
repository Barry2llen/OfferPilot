// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import i18n from "@/app/lib/i18n";
import ThinkingControl from "./thinking-control";

afterEach(cleanup);

it("offers provider-specific thinking controls and submits a selected value", async () => {
  await i18n.changeLanguage("en-US");
  const onChange = vi.fn();
  render(<ThinkingControl provider="Google" value={{ type: "level", value: null }} onChange={onChange} />);
  expect(screen.getByRole("combobox", { name: "Thinking value" })).toBeTruthy();
  fireEvent.change(screen.getByRole("combobox", { name: "Thinking" }), { target: { value: "budget" } });
  expect(onChange).toHaveBeenCalledWith({ type: "budget", value: null });
});

it("shows the Anthropic budget fields in Chinese", async () => {
  await i18n.changeLanguage("zh-CN");
  const onChange = vi.fn();
  render(<ThinkingControl provider="Anthropic" value={{ type: "budget", value: null, max_tokens: null }} onChange={onChange} />);
  expect(screen.getByText("思考设置")).toBeTruthy();
  expect(screen.getByRole("spinbutton", { name: "思考预算（token）" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("输出 token 上限"), { target: { value: "4096" } });
  expect(onChange).toHaveBeenCalledWith({ type: "budget", value: null, max_tokens: 4096 });
});
