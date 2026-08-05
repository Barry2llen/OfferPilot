import { useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@/app/components/ui/button";
import type {
  Provider,
  ModelProviderCreate,
  ModelProviderResponse,
  ModelProviderUpdate,
} from "@/app/lib/api/types";

interface ProviderFormProps {
  initial?: ModelProviderResponse;
  onSubmit: (data: ModelProviderCreate | ModelProviderUpdate) => Promise<void>;
  onCancel: () => void;
  submitting: boolean;
}

const providerOptions: { value: Provider; label: string }[] = [
  { value: "OpenAI", label: "OpenAI" },
  { value: "Google", label: "Google" },
  { value: "Anthropic", label: "Anthropic" },
  { value: "DeepSeek", label: "DeepSeek" },
  { value: "OpenAI Compatible", label: "OpenAI Compatible" },
];

export default function ProviderForm({
  initial,
  onSubmit,
  onCancel,
  submitting,
}: ProviderFormProps) {
  const { t } = useTranslation();
  const [provider, setProvider] = useState<Provider>(
    (initial?.provider as Provider) || "OpenAI"
  );
  const [name, setName] = useState(initial?.name || "");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url || "");
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);

  const isEdit = !!initial;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const data: ModelProviderCreate | ModelProviderUpdate = isEdit
      ? {
          provider,
          base_url: baseUrl || null,
        }
      : {
          provider,
          name,
        };

    if (!isEdit && baseUrl) {
      data.base_url = baseUrl;
    }

    if (isEdit) {
      if (clearKey) {
        data.api_key = null;
      } else if (apiKey) {
        data.api_key = apiKey;
      }
    } else if (apiKey) {
      data.api_key = apiKey;
    }

    await onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          {t("settings.providerType")}
        </label>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as Provider)}
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 disabled:opacity-50 disabled:bg-surface-secondary"
        >
          {providerOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          {t("settings.configName")}
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("settings.configNamePlaceholder")}
          disabled={isEdit}
          required
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 disabled:opacity-50 disabled:bg-surface-secondary"
        />
        <p className="text-xs text-text-muted mt-1">
          {t("settings.configNameDescription")}
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          {t("settings.baseUrl")}
          <span className="text-text-muted font-normal ml-1">({t("settings.baseUrlOptional")})</span>
        </label>
        <input
          type="url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.example.com/v1"
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
        <p className="text-xs text-text-muted mt-1">
          {t("settings.baseUrlDescription")}
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          {t("settings.apiKey")}
          <span className="text-text-muted font-normal ml-1">
            ({isEdit ? t("settings.apiKeyKeep") : t("settings.apiKeyOptional")})
          </span>
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => {
            setApiKey(e.target.value);
            if (e.target.value) {
              setClearKey(false);
            }
          }}
          placeholder={isEdit ? t("settings.apiKeyPlaceholder") : t("settings.apiKeyNewPlaceholder")}
          autoComplete="off"
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
        {isEdit && (
          <label className="flex items-center gap-2 mt-2 cursor-pointer">
            <input
              type="checkbox"
              checked={clearKey}
              onChange={(e) => setClearKey(e.target.checked)}
              disabled={!!apiKey}
              className="rounded"
            />
            <span className="text-xs text-text-muted">{t("settings.clearApiKey")}</span>
          </label>
        )}
      </div>

      <div className="flex gap-3 pt-2">
        <Button type="submit" disabled={submitting || !name} className="flex-1">
          {submitting ? t("common.saving") : isEdit ? t("settings.save") : t("common.create")}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={submitting}
          className="flex-1"
        >
          {t("common.cancel")}
        </Button>
      </div>
    </form>
  );
}
