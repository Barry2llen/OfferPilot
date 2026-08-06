import { useEffect, useState, type ChangeEvent } from "react";
import { Link } from "react-router";
import { useTranslation } from "react-i18next";
import { contextCompactionSettingsApi } from "@/app/lib/api/context-compaction-settings";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import Badge from "@/app/components/ui/badge";
import Button, { buttonClassName } from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import { Skeleton } from "@/app/components/ui/skeleton";
import type {
  ContextCompactionSettingsResponse,
  ModelSelectionResponse,
} from "@/app/lib/api/types";

interface AdvancedSettingsData {
  selections: ModelSelectionResponse[];
  contextCompactionSettings: ContextCompactionSettingsResponse;
}

const EMPTY_SELECTIONS: ModelSelectionResponse[] = [];

export default function AdvancedSettingsPage() {
  const { t } = useTranslation();
  const { data, loading, error, refetch } = useAsyncData<AdvancedSettingsData>(
    async () => {
      const [selections, contextCompactionSettings] = await Promise.all([
        modelSelectionsApi.list(),
        contextCompactionSettingsApi.get(),
      ]);
      return { selections, contextCompactionSettings };
    },
  );
  const { addToast } = useToast();
  const selections = data?.selections ?? EMPTY_SELECTIONS;
  const contextCompactionSettings = data?.contextCompactionSettings;
  const [compactionModelSelectionId, setCompactionModelSelectionId] =
    useState<number | null>(null);
  const [compactionSettingsSubmitting, setCompactionSettingsSubmitting] =
    useState(false);

  useEffect(() => {
    if (contextCompactionSettings) {
      setCompactionModelSelectionId(
        contextCompactionSettings.model_selection_id,
      );
    }
  }, [contextCompactionSettings]);

  const handleCompactionModelChange = async (
    event: ChangeEvent<HTMLSelectElement>,
  ) => {
    const previous = compactionModelSelectionId;
    const next = event.target.value ? Number(event.target.value) : null;
    setCompactionModelSelectionId(next);
    setCompactionSettingsSubmitting(true);
    try {
      const updated = await contextCompactionSettingsApi.update({
        model_selection_id: next,
      });
      setCompactionModelSelectionId(updated.model_selection_id);
      addToast(t("settings.contextCompactionUpdated"), "success");
    } catch (err: unknown) {
      setCompactionModelSelectionId(previous);
      const msg =
        err instanceof Error ? err.message : t("settings.operationFailed");
      addToast(msg, "error");
    } finally {
      setCompactionSettingsSubmitting(false);
    }
  };

  if (loading) {
    return <Skeleton className="h-56 rounded-[20px]" />;
  }

  if (error) {
    return (
      <div className="py-20 text-center">
        <p className="mb-4 text-sm text-error-text">{error}</p>
        <Button variant="secondary" onClick={refetch}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  return (
    <Card className="max-w-3xl" padding="lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-display text-lg font-semibold text-text-primary">
              {t("settings.contextCompactionTitle")}
            </h2>
            <Badge variant="info" size="sm">
              {t("settings.advancedTab")}
            </Badge>
          </div>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-text-muted">
            {t("settings.contextCompactionDescription")}
          </p>
        </div>
      </div>

      <label className="mt-6 block text-sm font-medium text-text-primary">
        {t("settings.contextCompactionModel")}
        <select
          className="mt-2 h-11 w-full rounded-xl border border-border-default bg-white px-3 text-sm text-text-primary outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20"
          value={compactionModelSelectionId ?? ""}
          onChange={handleCompactionModelChange}
          disabled={compactionSettingsSubmitting}
        >
          <option value="">
            {t("settings.followCurrentConversationModel")}
          </option>
          {selections.map((selection) => (
            <option key={selection.id} value={selection.id}>
              {selection.provider.name} / {selection.model_name}
            </option>
          ))}
        </select>
      </label>

      {compactionSettingsSubmitting ? (
        <p className="mt-2 text-xs text-text-muted">{t("common.saving")}</p>
      ) : null}

      {selections.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-border-default bg-surface-secondary/50 px-4 py-4">
          <p className="text-sm leading-6 text-text-secondary">
            {t("settings.noCompactionModels")}
          </p>
          <Link
            to="/settings/providers"
            className={buttonClassName({
              variant: "secondary",
              size: "sm",
              className: "mt-3",
            })}
          >
            {t("settings.goToModelConfig")}
          </Link>
        </div>
      ) : null}
    </Card>
  );
}
