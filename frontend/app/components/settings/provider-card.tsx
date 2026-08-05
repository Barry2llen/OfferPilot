import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Card from "@/app/components/ui/card";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import type { ModelProviderResponse } from "@/app/lib/api/types";

interface ProviderCardProps {
  provider: ModelProviderResponse;
  onEdit: (provider: ModelProviderResponse) => void;
  onDelete: (provider: ModelProviderResponse) => void;
  onAddModel?: (provider: ModelProviderResponse) => void;
  deleting: boolean;
  children?: ReactNode;
  highlight?: boolean;
}

export default function ProviderCard({
  provider,
  onEdit,
  onDelete,
  onAddModel,
  deleting,
  children,
  highlight = false,
}: ProviderCardProps) {
  const { t } = useTranslation();
  const shouldShowBaseUrl =
    provider.provider === "OpenAI Compatible" && !!provider.base_url;

  return (
    <Card
      className={`transition-all duration-1000 ${highlight ? "ring-2 ring-primary-500 bg-primary-50 shadow-brand-glow" : ""}`}
    >
      <div>
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <h3 className="font-display text-base font-semibold text-text-primary truncate">
                {provider.name}
              </h3>
              <Badge
                variant={provider.has_api_key ? "success" : "warning"}
                size="sm"
              >
                {provider.has_api_key ? t("settings.configuredKey") : t("settings.unconfiguredKey")}
              </Badge>
            </div>
            <p className="text-sm text-text-secondary mb-2">
              {provider.provider}
              {shouldShowBaseUrl && (
                <span className="mt-1 block truncate font-mono text-xs text-text-muted">
                  {provider.base_url}
                </span>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2 shrink-0">
            {onAddModel && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => onAddModel(provider)}
              >
                {t("settings.addModel")}
              </Button>
            )}
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onEdit(provider)}
              >
                {t("settings.edit")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDelete(provider)}
                disabled={deleting}
                className="text-error-text hover:bg-error-bg"
              >
                {deleting ? t("settings.deleting") : t("settings.delete")}
              </Button>
            </div>
          </div>
        </div>

        {children && (
          <div className="mt-4 border-t border-border-light pt-4">
            {children}
          </div>
        )}
      </div>
    </Card>
  );
}
