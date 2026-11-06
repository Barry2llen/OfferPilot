import { ChevronDown } from "lucide-react";
import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Select from "@/app/components/ui/select";
import { selectMenuClassName, selectTriggerClassName } from "@/app/components/ui/select-styles";
import { useDismiss } from "@/app/hooks/use-dismiss";
import type { ModelSelectionResponse } from "@/app/lib/api/types";
import { formatLocaleNumber } from "@/app/lib/i18n";
import { defaultThinkingType, providerThinkingTypes, thinkingValueOptions } from "@/app/lib/thinking";

export interface ThinkingOverride {
  value: string | number | null;
}

const DEFAULT_OPTION = "__default";

/**
 * Per-request thinking intensity for the composer. "Default" clears the override
 * so the model selection's saved thinking setting applies.
 */
export default function ThinkingPicker({ model, override, onChange, disabled = false }: {
  model: ModelSelectionResponse | undefined;
  override: ThinkingOverride | undefined;
  onChange: (override: ThinkingOverride | undefined) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const budgetId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [budgetOpen, setBudgetOpen] = useState(false);
  useDismiss(rootRef, budgetOpen, () => setBudgetOpen(false));

  if (!model) return null;
  const provider = model.provider.provider;
  if (!providerThinkingTypes[provider]?.length) return null;

  const type = model.thinking?.type ?? defaultThinkingType(provider);
  const savedValue = model.thinking?.value ?? null;
  const valueLabel = (value: string | number | null) =>
    value === null
      ? t("settings.providerDefault")
      : typeof value === "number"
        ? formatLocaleNumber(value)
        : t(`settings.thinkingValue_${value}`);
  const current = override && override.value !== null ? override.value : null;
  const triggerLabel = current !== null ? valueLabel(current) : savedValue !== null ? valueLabel(savedValue) : t("chat.thinkingDefaultShort");
  const triggerContent = (
    <span className="flex min-w-0 items-center gap-1">
      <span className="hidden text-text-muted sm:inline">{t("chat.thinkingLabel")}</span>
      <span className="truncate">{triggerLabel}</span>
    </span>
  );

  if (type !== "budget") {
    return (
      <Select
        aria-label={t("chat.thinkingIntensity")}
        title={t("chat.thinkingIntensity")}
        variant="ghost"
        size="sm"
        placement="top"
        align="end"
        disabled={disabled}
        triggerClassName="h-9 rounded-full px-3"
        value={typeof current === "string" ? current : DEFAULT_OPTION}
        renderValue={() => triggerContent}
        onChange={(value) => onChange(value === DEFAULT_OPTION ? undefined : { value })}
        options={[
          { value: DEFAULT_OPTION, label: t("chat.thinkingDefault", { value: valueLabel(savedValue) }) },
          ...thinkingValueOptions[type].map((value) => ({ value, label: t(`settings.thinkingValue_${value}`) })),
        ]}
      />
    );
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        data-open={budgetOpen}
        aria-label={t("chat.thinkingIntensity")}
        title={t("chat.thinkingIntensity")}
        aria-haspopup="dialog"
        aria-expanded={budgetOpen}
        onClick={() => setBudgetOpen((open) => !open)}
        className={`${selectTriggerClassName("sm", "ghost")} h-9 rounded-full px-3`}
      >
        {triggerContent}
        <ChevronDown size={14} aria-hidden="true" className={`shrink-0 text-text-muted transition-transform ${budgetOpen ? "rotate-180" : ""}`} />
      </button>
      {budgetOpen && (
        <div role="dialog" aria-label={t("chat.thinkingIntensity")} className={`${selectMenuClassName} bottom-[calc(100%+6px)] right-0 w-60 p-3`}>
          <label htmlFor={budgetId} className="text-xs font-medium text-text-secondary">{t("settings.thinkingBudget")}</label>
          <input
            id={budgetId}
            type="number"
            min={provider === "Anthropic" ? 1024 : -1}
            value={typeof current === "number" ? current : ""}
            placeholder={valueLabel(savedValue)}
            onChange={(event) => onChange(event.target.value === "" ? undefined : { value: Number(event.target.value) })}
            className="mt-1.5 h-9 w-full rounded-lg border border-border-default bg-surface-primary px-2.5 text-sm text-text-primary"
          />
          <button
            type="button"
            onClick={() => {
              onChange(undefined);
              setBudgetOpen(false);
            }}
            className="mt-2 w-full rounded-lg px-2.5 py-1.5 text-left text-xs text-text-secondary transition hover:bg-surface-secondary hover:text-text-primary"
          >
            {t("chat.thinkingUseDefault")} · {valueLabel(savedValue)}
          </button>
        </div>
      )}
    </div>
  );
}
