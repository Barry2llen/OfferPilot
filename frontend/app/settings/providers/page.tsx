import { FileText, Image } from "lucide-react";
import { useMemo, useState, useCallback, useEffect, type ChangeEvent } from "react";
import { useTranslation } from "react-i18next";
import { modelProvidersApi } from "@/app/lib/api/model-providers";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { contextCompactionSettingsApi } from "@/app/lib/api/context-compaction-settings";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ProviderCard from "@/app/components/settings/provider-card";
import ProviderForm from "@/app/components/settings/provider-form";
import SelectionForm from "@/app/components/settings/selection-form";
import FormDrawer from "@/app/components/ui/form-drawer";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import { Skeleton } from "@/app/components/ui/skeleton";
import { formatLocaleNumber } from "@/app/lib/i18n";
import type {
  ModelProviderResponse,
  ModelProviderCreate,
  ModelProviderUpdate,
  ModelSelectionResponse,
  ModelSelectionCreate,
  ModelSelectionUpdate,
  ContextCompactionSettingsResponse,
} from "@/app/lib/api/types";

interface ModelConfigData {
  providers: ModelProviderResponse[];
  selections: ModelSelectionResponse[];
  contextCompactionSettings: ContextCompactionSettingsResponse;
}

const EMPTY_PROVIDERS: ModelProviderResponse[] = [];
const EMPTY_SELECTIONS: ModelSelectionResponse[] = [];
const PAGE_CANVAS_CLASS = "electron-titlebar-safe-top min-h-full bg-white";
const PAGE_INNER_CLASS =
  "mx-auto max-w-[1040px] px-5 py-4 sm:px-8 lg:px-10 lg:py-6";

export default function ProvidersPage() {
  const { t } = useTranslation();
  const { data, loading, error, refetch } = useAsyncData<ModelConfigData>(
    async () => {
      const [providers, selections] = await Promise.all([
        modelProvidersApi.list(),
        modelSelectionsApi.list(),
      ]);
      const contextCompactionSettings =
        await contextCompactionSettingsApi.get();
      return { providers, selections, contextCompactionSettings };
    },
  );

  const { addToast } = useToast();
  const providers = data?.providers ?? EMPTY_PROVIDERS;
  const selections = data?.selections ?? EMPTY_SELECTIONS;
  const [compactionModelSelectionId, setCompactionModelSelectionId] =
    useState<number | null>(null);
  const [compactionSettingsSubmitting, setCompactionSettingsSubmitting] =
    useState(false);
  useEffect(() => {
    if (data?.contextCompactionSettings) {
      setCompactionModelSelectionId(
        data.contextCompactionSettings.model_selection_id,
      );
    }
  }, [data?.contextCompactionSettings]);
  const selectionsByProvider = useMemo(() => {
    const grouped = new Map<string, ModelSelectionResponse[]>();
    for (const selection of selections) {
      const providerName = selection.provider.name;
      const items = grouped.get(providerName) ?? [];
      items.push(selection);
      grouped.set(providerName, items);
    }
    return grouped;
  }, [selections]);

  const [providerDrawerOpen, setProviderDrawerOpen] = useState(false);
  const [selectionDrawerOpen, setSelectionDrawerOpen] = useState(false);
  const [highlightProvider, setHighlightProvider] = useState<string | null>(
    null,
  );
  const [editingProvider, setEditingProvider] =
    useState<ModelProviderResponse | null>(null);
  const [editingSelection, setEditingSelection] =
    useState<ModelSelectionResponse | null>(null);
  const [defaultProviderName, setDefaultProviderName] = useState("");
  const [providerSubmitting, setProviderSubmitting] = useState(false);
  const [selectionSubmitting, setSelectionSubmitting] = useState(false);
  const [deletingProvider, setDeletingProvider] = useState<string | null>(null);
  const [deletingSelection, setDeletingSelection] = useState<number | null>(
    null,
  );
  const [confirmProviderDelete, setConfirmProviderDelete] =
    useState<ModelProviderResponse | null>(null);
  const [confirmSelectionDelete, setConfirmSelectionDelete] =
    useState<ModelSelectionResponse | null>(null);

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

  const handleProviderCreate = () => {
    setEditingProvider(null);
    setProviderDrawerOpen(true);
  };

  const handleProviderEdit = (provider: ModelProviderResponse) => {
    setEditingProvider(provider);
    setProviderDrawerOpen(true);
  };

  const handleSelectionCreate = (providerName: string) => {
    setEditingSelection(null);
    setDefaultProviderName(providerName);
    setSelectionDrawerOpen(true);
  };

  const handleSelectionEdit = (selection: ModelSelectionResponse) => {
    setEditingSelection(selection);
    setDefaultProviderName(selection.provider.name);
    setSelectionDrawerOpen(true);
  };

  const handleProviderSubmit = useCallback(
    async (data: ModelProviderCreate | ModelProviderUpdate) => {
      setProviderSubmitting(true);
      try {
        if (editingProvider) {
          await modelProvidersApi.update(
            editingProvider.name,
            data as ModelProviderUpdate,
          );
          addToast(t("settings.providerUpdated"), "success");
        } else {
          const createData = data as ModelProviderCreate;
          await modelProvidersApi.create(createData);
          addToast(t("settings.providerCreated"), "success");
          setHighlightProvider(createData.name);
          setTimeout(() => setHighlightProvider(null), 3000);
        }
        setProviderDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : t("settings.operationFailed");
        addToast(msg, "error");
      } finally {
        setProviderSubmitting(false);
      }
    },
    [editingProvider, refetch, addToast, t],
  );

  const handleSelectionSubmit = useCallback(
    async (data: ModelSelectionCreate | ModelSelectionUpdate) => {
      setSelectionSubmitting(true);
      try {
        if (editingSelection) {
          await modelSelectionsApi.update(
            editingSelection.id,
            data as ModelSelectionUpdate,
          );
          addToast(t("settings.selectionUpdated"), "success");
        } else {
          await modelSelectionsApi.create(data as ModelSelectionCreate);
          addToast(t("settings.selectionCreated"), "success");
        }
        setSelectionDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : t("settings.operationFailed");
        addToast(msg, "error");
      } finally {
        setSelectionSubmitting(false);
      }
    },
    [editingSelection, refetch, addToast, t],
  );

  const handleProviderDelete = async () => {
    if (!confirmProviderDelete) return;
    setDeletingProvider(confirmProviderDelete.name);
    try {
      await modelProvidersApi.delete(confirmProviderDelete.name);
      addToast(t("settings.providerDeleted"), "success");
      setConfirmProviderDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("settings.deleteFailed");
      addToast(msg, "error");
    } finally {
      setDeletingProvider(null);
    }
  };

  const handleSelectionDelete = async () => {
    if (!confirmSelectionDelete) return;
    setDeletingSelection(confirmSelectionDelete.id);
    try {
      await modelSelectionsApi.delete(confirmSelectionDelete.id);
      addToast(t("settings.selectionDeleted"), "success");
      setConfirmSelectionDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t("settings.deleteFailed");
      addToast(msg, "error");
    } finally {
      setDeletingSelection(null);
    }
  };

  if (loading) {
    return (
      <div className={PAGE_CANVAS_CLASS}>
        <div className={PAGE_INNER_CLASS}>
          <div className="mb-6 flex items-center justify-between">
            <div>
              <Skeleton className="mb-2 h-8 w-32 rounded-lg" />
              <Skeleton className="h-4 w-56 rounded-lg" />
            </div>
            <Skeleton className="h-10 w-28 rounded-xl" />
          </div>
          <div className="space-y-3">
            {[1, 2, 3].map((item) => (
              <Skeleton key={item} className="h-32 rounded-[20px]" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={PAGE_CANVAS_CLASS}>
        <div className={PAGE_INNER_CLASS}>
          <div className="py-20 text-center">
            <p className="mb-4 text-sm text-error-text">{error}</p>
            <Button variant="secondary" onClick={refetch}>
              {t("common.retry")}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={PAGE_CANVAS_CLASS}>
      <div className={PAGE_INNER_CLASS}>
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold text-text-primary">
              {t("settings.title")}
            </h1>
            <p className="text-sm text-text-muted mt-1">
              {t("settings.description")}
            </p>
          </div>
          <Button onClick={handleProviderCreate}>{t("settings.addProvider")}</Button>
        </div>

        <section className="mb-6 rounded-[20px] border border-border-light bg-surface-secondary/60 p-5">
          <div className="mb-3">
            <h2 className="text-sm font-semibold text-text-primary">
              {t("settings.contextCompactionTitle")}
            </h2>
            <p className="mt-1 text-xs leading-5 text-text-muted">
              {t("settings.contextCompactionDescription")}
            </p>
          </div>
          <label className="block text-sm font-medium text-text-primary">
            {t("settings.contextCompactionModel")}
            <select
              className="mt-2 h-10 w-full rounded-lg border border-border-default bg-white px-3 text-sm text-text-primary outline-none focus:border-primary-500 focus:ring-2 focus:ring-primary-500/20 sm:max-w-[520px]"
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
            <p className="mt-2 text-xs text-text-muted">
              {t("common.saving")}
            </p>
          ) : null}
        </section>

        {providers && providers.length === 0 ? (
          <div className="text-center py-16 border-2 border-dashed border-border-default rounded-[20px]">
            <p className="text-text-muted text-sm mb-3">{t("settings.noProviders")}</p>
            <Button variant="secondary" onClick={handleProviderCreate}>
              {t("settings.createFirstProvider")}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {providers.map((provider) => {
              const providerSelections =
                selectionsByProvider.get(provider.name) ?? [];
              return (
                <ProviderCard
                  key={provider.name}
                  provider={provider}
                  onEdit={handleProviderEdit}
                  onDelete={setConfirmProviderDelete}
                  onAddModel={() => handleSelectionCreate(provider.name)}
                  deleting={deletingProvider === provider.name}
                  highlight={highlightProvider === provider.name}
                >
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-3">
                      <h4 className="text-sm font-medium text-text-primary">
                        {t("settings.modelSelections")}
                      </h4>
                      <span className="text-xs text-text-muted">
                        {t("settings.modelCount", {
                          count: formatLocaleNumber(providerSelections.length),
                        })}
                      </span>
                    </div>

                    {providerSelections.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-border-default px-4 py-5 text-center">
                        <p className="text-sm text-text-muted mb-3">
                          {t("settings.noProviderModels")}
                        </p>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleSelectionCreate(provider.name)}
                        >
                          {t("settings.addModel")}
                        </Button>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {providerSelections.map((selection) => (
                          <div
                            key={selection.id}
                            className="group/model-row rounded-xl border border-border-light bg-surface-secondary/60 px-4 py-3"
                          >
                            <div className="flex min-h-8 flex-wrap items-center justify-between gap-3">
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <h5 className="text-sm font-medium text-text-primary break-all">
                                    {selection.model_name}
                                  </h5>
                                  <ModelCapabilityIcon
                                    supportsImage={
                                      selection.supports_image_input
                                    }
                                  />
                                  {selection.provider.has_api_key ? null : (
                                    <Badge variant="warning" size="sm">
                                      {t("settings.missingKey")}
                                    </Badge>
                                  )}
                                </div>
                              </div>
                              <div className="flex shrink-0 items-center gap-2 opacity-0 transition-opacity duration-150 group-hover/model-row:opacity-100 group-focus-within/model-row:opacity-100">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleSelectionEdit(selection)}
                                >
                                  {t("settings.edit")}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    setConfirmSelectionDelete(selection)
                                  }
                                  disabled={deletingSelection === selection.id}
                                  className="text-error-text hover:bg-error-bg"
                                >
                                  {deletingSelection === selection.id
                                    ? t("settings.deleting")
                                    : t("settings.delete")}
                                </Button>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </ProviderCard>
              );
            })}
          </div>
        )}

        <FormDrawer
          open={providerDrawerOpen}
          title={editingProvider ? t("settings.editProvider") : t("settings.addProviderTitle")}
          onClose={() => setProviderDrawerOpen(false)}
        >
          <ProviderForm
            initial={editingProvider ?? undefined}
            onSubmit={handleProviderSubmit}
            onCancel={() => setProviderDrawerOpen(false)}
            submitting={providerSubmitting}
          />
        </FormDrawer>

        <FormDrawer
          open={selectionDrawerOpen}
          title={editingSelection ? t("settings.editSelection") : t("settings.addSelection")}
          onClose={() => setSelectionDrawerOpen(false)}
        >
          <SelectionForm
            initial={editingSelection ?? undefined}
            providers={providers}
            defaultProviderName={defaultProviderName}
            onSubmit={handleSelectionSubmit}
            onCancel={() => setSelectionDrawerOpen(false)}
            submitting={selectionSubmitting}
          />
        </FormDrawer>

        <ConfirmDialog
          open={!!confirmProviderDelete}
          title={t("settings.deleteProviderTitle")}
          message={t("settings.deleteProviderMessage", {
            name: confirmProviderDelete?.name,
          })}
          confirmLabel={t("settings.delete")}
          variant="danger"
          onConfirm={handleProviderDelete}
          onCancel={() => setConfirmProviderDelete(null)}
          loading={!!deletingProvider}
        />

        <ConfirmDialog
          open={!!confirmSelectionDelete}
          title={t("settings.deleteSelectionTitle")}
          message={t("settings.deleteSelectionMessage", {
            name: `${confirmSelectionDelete?.provider.name} / ${confirmSelectionDelete?.model_name}`,
          })}
          confirmLabel={t("settings.delete")}
          variant="danger"
          onConfirm={handleSelectionDelete}
          onCancel={() => setConfirmSelectionDelete(null)}
          loading={!!deletingSelection}
        />
      </div>
    </div>
  );
}

function ModelCapabilityIcon({ supportsImage }: { supportsImage: boolean }) {
  const { t } = useTranslation();
  const label = supportsImage ? t("settings.imageSupported") : t("settings.textOnly");
  const Icon = supportsImage ? Image : FileText;
  const className = supportsImage
    ? "bg-success-bg text-success-text"
    : "bg-surface-secondary text-text-muted";

  return (
    <span
      aria-label={label}
      title={label}
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${className}`}
    >
      <Icon aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2} />
    </span>
  );
}
