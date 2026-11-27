// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AppProvider, useAppActions, useAppContext } from "./app-context";

vi.mock("@/app/hooks/use-analysis-events", () => ({ useAnalysisEvents: () => {} }));

const storageKey = "offerpilot.chat.selection";

afterEach(() => {
  cleanup();
  localStorage.removeItem(storageKey);
});

function renderSelection() {
  return renderHook(() => ({
    model: useAppContext().state.currentModelSelection,
    actions: useAppActions(),
  }), { wrapper: AppProvider });
}

it("keeps the first model default after repeated initialization", () => {
  const { result } = renderSelection();
  expect(JSON.parse(localStorage.getItem(storageKey)!)).not.toHaveProperty("model");

  act(() => {
    result.current.actions.initializeModelSelection(1);
    result.current.actions.initializeModelSelection(2);
  });

  expect(result.current.model).toBe(1);
  expect(JSON.parse(localStorage.getItem(storageKey)!)).toHaveProperty("model", 1);
});

it("preserves an empty choice when another page loads models or the app reloads", () => {
  const { result, unmount } = renderSelection();
  act(() => {
    result.current.actions.setModelSelection(null);
    result.current.actions.initializeModelSelection(1);
  });
  expect(result.current.model).toBeNull();
  expect(JSON.parse(localStorage.getItem(storageKey)!)).toHaveProperty("model", null);

  unmount();
  const reopened = renderSelection();
  act(() => reopened.result.current.actions.initializeModelSelection(3));
  expect(reopened.result.current.model).toBeNull();
});
