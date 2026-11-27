import { Check, ChevronDown } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { shouldOpenUpward, useDismiss } from "@/app/hooks/use-dismiss";
import { selectMenuClassName, selectTriggerClassName } from "@/app/components/ui/select-styles";

export interface SelectOption<T extends string = string> {
  value: T;
  label: string;
  description?: string;
}

export interface SelectProps<T extends string = string> {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  /** Lets a `<label htmlFor>` name the trigger. */
  id?: string;
  "aria-label"?: string;
  title?: string;
  disabled?: boolean;
  size?: "sm" | "md";
  variant?: "outline" | "ghost";
  placement?: "auto" | "top" | "bottom";
  align?: "start" | "end";
  /** Leading icon inside the trigger. */
  icon?: ReactNode;
  /** Trigger content; defaults to the selected option's label. */
  renderValue?: (option: SelectOption<T> | undefined) => ReactNode;
  placeholder?: string;
  className?: string;
  triggerClassName?: string;
  menuClassName?: string;
}

const OPTION_HEIGHT = 38;
const MENU_MAX_HEIGHT = 288;

/** Select-only combobox: the trigger keeps focus and drives a listbox through aria-activedescendant. */
export default function Select<T extends string = string>({
  value,
  options,
  onChange,
  id,
  "aria-label": ariaLabel,
  title,
  disabled = false,
  size = "md",
  variant = "outline",
  placement = "auto",
  align = "start",
  icon,
  renderValue,
  placeholder,
  className = "",
  triggerClassName = "",
  menuClassName = "",
}: SelectProps<T>) {
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const baseId = useId();
  const listId = `${baseId}-listbox`;
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [upward, setUpward] = useState(placement === "top");

  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;
  const optionId = (index: number) => `${baseId}-option-${index}`;

  const close = (restoreFocus = false) => {
    setOpen(false);
    setActive(-1);
    if (restoreFocus) triggerRef.current?.focus();
  };

  useDismiss(rootRef, open, () => close());

  useEffect(() => {
    if (!open || active < 0) return;
    document.getElementById(`${baseId}-option-${active}`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open, baseId]);

  const openMenu = (index = selectedIndex) => {
    if (disabled || options.length === 0) return;
    const menuHeight = Math.min(options.length * OPTION_HEIGHT + 8, MENU_MAX_HEIGHT);
    setUpward(
      placement === "top" ||
        (placement === "auto" && shouldOpenUpward(triggerRef.current, menuHeight)),
    );
    setActive(index >= 0 ? index : 0);
    setOpen(true);
  };

  const commit = (index: number) => {
    const option = options[index];
    if (option && option.value !== value) onChange(option.value);
    close(true);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        if (open) setActive((index) => Math.min(options.length - 1, index + 1));
        else openMenu();
        break;
      case "ArrowUp":
        event.preventDefault();
        if (open) setActive((index) => Math.max(0, index - 1));
        else openMenu();
        break;
      case "Home":
        if (open) {
          event.preventDefault();
          setActive(0);
        }
        break;
      case "End":
        if (open) {
          event.preventDefault();
          setActive(options.length - 1);
        }
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        if (open) commit(active);
        else openMenu();
        break;
      case "Escape":
        if (open) {
          // Keep an enclosing <dialog> open; only the menu closes.
          event.preventDefault();
          event.stopPropagation();
          close(true);
        }
        break;
      case "Tab":
        if (open) close();
        break;
    }
  };

  return (
    <div ref={rootRef} className={`relative inline-flex min-w-0 ${className}`}>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        title={title}
        disabled={disabled}
        data-open={open}
        onClick={() => (open ? close() : openMenu())}
        onKeyDown={handleKeyDown}
        onKeyUp={(event) => {
          if (event.key === " ") event.preventDefault();
        }}
        className={`${selectTriggerClassName(size, variant)} w-full ${triggerClassName}`}
      >
        {icon && <span className="flex shrink-0 items-center text-text-muted">{icon}</span>}
        <span className="min-w-0 flex-1 truncate">
          {renderValue ? renderValue(selected) : selected?.label ?? placeholder ?? ""}
        </span>
        <ChevronDown
          aria-hidden="true"
          size={size === "sm" ? 14 : 16}
          className={`shrink-0 text-text-muted transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label={ariaLabel}
          tabIndex={-1}
          onMouseDown={(event) => event.preventDefault()}
          className={`${selectMenuClassName} max-h-72 w-max min-w-full max-w-[min(22rem,calc(100vw-2rem))] overflow-y-auto overscroll-contain p-1 ${
            upward ? "bottom-[calc(100%+6px)]" : "top-[calc(100%+6px)]"
          } ${align === "end" ? "right-0" : "left-0"} ${menuClassName}`}
        >
          {options.map((option, index) => {
            const isSelected = index === selectedIndex;
            return (
              <li
                key={option.value}
                id={optionId(index)}
                role="option"
                aria-selected={isSelected}
                onPointerMove={() => setActive(index)}
                onClick={() => commit(index)}
                className={`flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                  index === active ? "bg-surface-secondary" : ""
                } ${isSelected ? "font-medium text-text-primary" : "text-text-secondary"}`}
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{option.label}</span>
                  {option.description && (
                    <span className="block truncate text-xs font-normal text-text-muted">
                      {option.description}
                    </span>
                  )}
                </span>
                <Check
                  aria-hidden="true"
                  size={15}
                  className={`shrink-0 ${isSelected ? "opacity-100" : "opacity-0"}`}
                />
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
