import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import Button from "@/app/components/ui/button";
import { modelProvidersApi } from "@/app/lib/api/model-providers";
import type {
  ModelSelectionCreate,
  ModelSelectionResponse,
  ModelProviderResponse,
  ModelSelectionUpdate,
} from "@/app/lib/api/types";

interface SelectionFormProps {
  initial?: ModelSelectionResponse;
  providers?: ModelProviderResponse[];
  defaultProviderName?: string;
  onSubmit: (data: ModelSelectionCreate | ModelSelectionUpdate) => Promise<void>;
  onCancel: () => void;
  submitting: boolean;
}

export default function SelectionForm({
  initial,
  providers: providedProviders,
  defaultProviderName,
  onSubmit,
  onCancel,
  submitting,
}: SelectionFormProps) {
  const { t } = useTranslation();
  const [providerName, setProviderName] = useState(
    initial?.provider.name || defaultProviderName || ""
  );
  const [modelName, setModelName] = useState(initial?.model_name || "");
  const [supportsImage, setSupportsImage] = useState(
    initial?.supports_image_input || false
  );
  const [fetchedProviders, setFetchedProviders] = useState<
    ModelProviderResponse[]
  >([]);

  const isEdit = !!initial;
  const providers = providedProviders ?? fetchedProviders;

  useEffect(() => {
    if (providedProviders) {
      return;
    }

    modelProvidersApi
      .list()
      .then(setFetchedProviders)
      .catch(() => {});
  }, [providedProviders]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await onSubmit({
      provider_name: providerName,
      model_name: modelName,
      supports_image_input: supportsImage,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          {t("settings.modelProvider")}
        </label>
        <select
          value={providerName}
          onChange={(e) => setProviderName(e.target.value)}
          required
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 disabled:opacity-50 disabled:bg-surface-secondary"
        >
          <option value="">{t("settings.chooseProvider")}</option>
          {providers.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name} ({p.provider}{" "}
              {p.has_api_key ? t("settings.providerConfigured") : t("settings.providerNotConfigured")})
            </option>
          ))}
        </select>
        {providers.length === 0 && (
          <p className="text-xs text-warning-text mt-1">
            {t("settings.noAvailableProviders")}
          </p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          {t("settings.modelName")}
        </label>
        <input
          type="text"
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          placeholder={t("settings.modelNamePlaceholder")}
          required
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
      </div>

      <div>
        <label className="flex items-center gap-3 cursor-pointer">
          <div className="relative">
            <input
              type="checkbox"
              checked={supportsImage}
              onChange={(e) => setSupportsImage(e.target.checked)}
              className="sr-only"
            />
            <div className={`w-9 h-5 rounded-full transition-colors ${supportsImage ? "bg-primary-500" : "bg-border-default"}`} />
            <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform ${supportsImage ? "translate-x-4" : "translate-x-0"}`} />
          </div>
          <span className="text-sm font-medium text-text-primary">
            {t("settings.imageInput")}
          </span>
          <span className="text-xs text-text-muted">
            {t("settings.imageInputDescription")}
          </span>
        </label>
      </div>

      <div className="flex gap-3 pt-2">
        <Button
          type="submit"
          disabled={submitting || !providerName || !modelName}
          className="flex-1"
        >
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
