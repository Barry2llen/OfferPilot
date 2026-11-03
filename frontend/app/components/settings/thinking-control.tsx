import { useTranslation } from "react-i18next";
import type { ThinkingSettings, ThinkingType } from "@/app/lib/api/types";
import { providerThinkingTypes } from "@/app/lib/thinking";
const values: Record<Exclude<ThinkingType, "budget">, string[]> = {
  effort: ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
  level: ["minimal", "low", "medium", "high"],
  deepseek: ["disabled", "low", "high", "max"],
  adaptive: ["low", "medium", "high", "xhigh", "max"],
};

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
  const inputClass = "rounded-lg border border-border-default bg-white px-2 py-1.5 text-sm text-text-primary";
  return <div className="flex flex-wrap items-center gap-2">
    <label className="text-sm text-text-secondary" htmlFor={allowType ? "thinking-type" : "chat-thinking-value"}>{t("settings.thinking")}</label>
    {allowType && <select id="thinking-type" className={inputClass} value={value.type} disabled={disabled} onChange={(e) => onChange({ type: e.target.value as ThinkingType, value: null })}>
      {types.map((type) => <option key={type} value={type}>{t(`settings.thinkingType_${type}`)}</option>)}
    </select>}
    {value.type === "budget" ? <>
      <input id={allowType ? undefined : "chat-thinking-value"} aria-label={t(allowType ? "settings.thinkingBudget" : "settings.thinking")} className={`${inputClass} w-32`} type="number" min={provider === "Anthropic" ? 1024 : -1} placeholder={t("settings.providerDefault")} value={value.value ?? ""} disabled={disabled} onChange={(e) => onChange({ ...value, value: e.target.value === "" ? null : Number(e.target.value) })} />
      {allowType && provider === "Anthropic" && <input className={`${inputClass} w-32`} type="number" min={1025} required={value.value !== null} aria-label={t("settings.maxTokens")} placeholder={t("settings.maxTokens")} value={value.max_tokens ?? ""} disabled={disabled} onChange={(e) => onChange({ ...value, max_tokens: e.target.value === "" ? null : Number(e.target.value) })} />}
    </> : <select id={allowType ? undefined : "chat-thinking-value"} aria-label={t(allowType ? "settings.thinkingValue" : "settings.thinking")} className={inputClass} value={value.value ?? ""} disabled={disabled} onChange={(e) => onChange({ ...value, value: e.target.value || null })}>
      <option value="">{t("settings.providerDefault")}</option>
      {values[value.type].map((item) => <option key={item} value={item}>{t(`settings.thinkingValue_${item}`)}</option>)}
    </select>}
  </div>;
}
