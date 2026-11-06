import { useTranslation } from "react-i18next";
import type { ThinkingSettings, ThinkingType } from "@/app/lib/api/types";
import Select from "@/app/components/ui/select";
import { providerThinkingTypes, thinkingValueOptions } from "@/app/lib/thinking";

export default function ThinkingControl({ provider, value, onChange, allowType = true, disabled = false }: {
  provider: string;
  value: ThinkingSettings;
  onChange: (value: ThinkingSettings) => void;
  allowType?: boolean;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const types = providerThinkingTypes[provider] ?? [];
  if (!types.length) return null;
  const inputClass = "h-9 rounded-lg border border-border-default bg-surface-primary px-2.5 text-sm text-text-primary";
  return <div className="flex flex-wrap items-center gap-2">
    <label className="text-sm text-text-secondary" htmlFor={allowType ? "thinking-type" : "chat-thinking-value"}>{t("settings.thinking")}</label>
    {allowType && <Select<ThinkingType> id="thinking-type" className="min-w-36" triggerClassName="h-9" value={value.type} disabled={disabled}
      options={types.map((type) => ({ value: type, label: t(`settings.thinkingType_${type}`) }))}
      onChange={(type) => onChange({ type, value: null })} />}
    {value.type === "budget" ? <>
      <input id={allowType ? undefined : "chat-thinking-value"} aria-label={t(allowType ? "settings.thinkingBudget" : "settings.thinking")} className={`${inputClass} w-32`} type="number" min={provider === "Anthropic" ? 1024 : -1} placeholder={t("settings.providerDefault")} value={value.value ?? ""} disabled={disabled} onChange={(e) => onChange({ ...value, value: e.target.value === "" ? null : Number(e.target.value) })} />
      {allowType && provider === "Anthropic" && <input className={`${inputClass} w-32`} type="number" min={1025} required={value.value !== null} aria-label={t("settings.maxTokens")} placeholder={t("settings.maxTokens")} value={value.max_tokens ?? ""} disabled={disabled} onChange={(e) => onChange({ ...value, max_tokens: e.target.value === "" ? null : Number(e.target.value) })} />}
    </> : <Select id={allowType ? undefined : "chat-thinking-value"} className="min-w-36" triggerClassName="h-9" aria-label={t(allowType ? "settings.thinkingValue" : "settings.thinking")}
      value={typeof value.value === "string" ? value.value : ""} disabled={disabled}
      options={[
        { value: "", label: t("settings.providerDefault") },
        ...thinkingValueOptions[value.type].map((item) => ({ value: item, label: t(`settings.thinkingValue_${item}`) })),
      ]}
      onChange={(next) => onChange({ ...value, value: next || null })} />}
  </div>;
}
