import Card from "@/app/components/ui/card";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import { useTranslation } from "react-i18next";
import type { ModelSelectionResponse } from "@/app/lib/api/types";

interface SelectionCardProps {
  selection: ModelSelectionResponse;
  onEdit: (selection: ModelSelectionResponse) => void;
  onDelete: (selection: ModelSelectionResponse) => void;
  deleting: boolean;
}

export default function SelectionCard({
  selection,
  onEdit,
  onDelete,
  deleting,
}: SelectionCardProps) {
  const { t } = useTranslation();
  return (
    <Card>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h3 className="font-display text-base font-semibold text-text-primary">
              {selection.model_name}
            </h3>
            <Badge variant="info" size="sm">
              ID: {selection.id}
            </Badge>
          </div>
          <p className="text-sm text-text-secondary">
            {t("settings.provider")}: {selection.provider.name} ({selection.provider.provider})
          </p>
          <div className="flex items-center gap-2 mt-1.5">
            <Badge
              variant={selection.supports_image_input ? "success" : "neutral"}
              size="sm"
            >
              {selection.supports_image_input ? t("settings.imageSupported") : t("settings.textOnly")}
            </Badge>
            {selection.provider.has_api_key ? null : (
              <Badge variant="warning" size="sm">
                {t("settings.missingKey")}
              </Badge>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" size="sm" onClick={() => onEdit(selection)}>
            {t("settings.edit")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(selection)}
            disabled={deleting}
            className="text-error-text hover:bg-error-bg"
          >
            {deleting ? t("settings.deleting") : t("settings.delete")}
          </Button>
        </div>
      </div>
    </Card>
  );
}
