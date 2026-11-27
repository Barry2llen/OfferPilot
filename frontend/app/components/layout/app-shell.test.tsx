// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import i18n from "@/app/lib/i18n";
import AppShell from "./app-shell";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function BrokenPage(): never {
  throw new Error("Route module could not load");
}

it("keeps the desktop window controls available when a page fails", async () => {
  await i18n.changeLanguage("en-US");
  vi.spyOn(console, "error").mockImplementation(() => {});
  const windowControls = {
    minimize: vi.fn(),
    toggleMaximize: vi.fn(),
    close: vi.fn(),
    isMaximized: async () => false,
    onMaximizedChange: () => () => {},
  };
  vi.stubGlobal("offerPilotRuntime", { platform: "win32", windowControls });

  const { container } = render(<MemoryRouter><AppShell><BrokenPage /></AppShell></MemoryRouter>);

  expect(screen.getByRole("heading", { name: i18n.t("app.errorTitle") })).toBeTruthy();
  expect(container.querySelector(".window-drag-region")).toBeTruthy();
  const controls = within(screen.getByRole("group", { name: i18n.t("window.controls") }));
  fireEvent.click(controls.getByRole("button", { name: i18n.t("window.minimize") }));
  fireEvent.click(controls.getByRole("button", { name: i18n.t("window.maximize") }));
  fireEvent.click(controls.getByRole("button", { name: i18n.t("window.close") }));
  expect(windowControls.minimize).toHaveBeenCalledOnce();
  expect(windowControls.toggleMaximize).toHaveBeenCalledOnce();
  expect(windowControls.close).toHaveBeenCalledOnce();
});
