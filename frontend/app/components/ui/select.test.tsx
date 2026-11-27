// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import Select from "./select";

afterEach(cleanup);

const options = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

it("opens a listbox on click and commits the clicked option", () => {
  const onChange = vi.fn();
  render(<Select aria-label="Letter" value="a" options={options} onChange={onChange} />);
  const combobox = screen.getByRole("combobox", { name: "Letter" });
  expect(combobox.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(combobox);
  expect(combobox.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByRole("option", { name: "Alpha" }).getAttribute("aria-selected")).toBe("true");
  fireEvent.click(screen.getByRole("option", { name: "Gamma" }));
  expect(onChange).toHaveBeenCalledWith("c");
  expect(screen.queryByRole("listbox")).toBeNull();
});

it("supports keyboard navigation through aria-activedescendant", () => {
  const onChange = vi.fn();
  render(<Select aria-label="Letter" value="a" options={options} onChange={onChange} />);
  const combobox = screen.getByRole("combobox", { name: "Letter" });
  fireEvent.keyDown(combobox, { key: "ArrowDown" });
  expect(screen.getByRole("listbox")).toBeTruthy();
  const first = combobox.getAttribute("aria-activedescendant");
  fireEvent.keyDown(combobox, { key: "ArrowDown" });
  expect(combobox.getAttribute("aria-activedescendant")).not.toBe(first);
  fireEvent.keyDown(combobox, { key: "End" });
  fireEvent.keyDown(combobox, { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith("c");
});

it("closes on Escape without changing the value and stays closed when disabled", () => {
  const onChange = vi.fn();
  const { rerender } = render(<Select aria-label="Letter" value="b" options={options} onChange={onChange} />);
  const combobox = screen.getByRole("combobox", { name: "Letter" });
  fireEvent.click(combobox);
  fireEvent.keyDown(combobox, { key: "Escape" });
  expect(screen.queryByRole("listbox")).toBeNull();
  expect(onChange).not.toHaveBeenCalled();
  rerender(<Select aria-label="Letter" value="b" options={options} onChange={onChange} disabled />);
  fireEvent.click(screen.getByRole("combobox", { name: "Letter" }));
  expect(screen.queryByRole("listbox")).toBeNull();
});

it("can be named by an external label", () => {
  render(<><label htmlFor="letter">Pick a letter</label><Select id="letter" value="a" options={options} onChange={() => {}} /></>);
  expect(screen.getByRole("combobox", { name: "Pick a letter" })).toBeTruthy();
});
