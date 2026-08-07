import { FileText, Image } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { modelProvidersApi } from "@/app/lib/api/model-providers";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ProviderForm from "@/app/components/settings/provider-form";
import SelectionForm from "@/app/components/settings/selection-form";
import FormDrawer from "@/app/components/ui/form-drawer";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Card from "@/app/components/ui/card";
import { Skeleton } from "@/app/components/ui/skeleton";
import { formatLocaleNumber } from "@/app/lib/i18n";
import type {
  ModelProviderResponse,
  ModelProviderCreate,
  ModelProviderUpdate,
  ModelSelectionResponse,
  ModelSelectionCreate,
  ModelSelectionUpdate,
} from "@/app/lib/api/types";

interface ModelConfigData {
  providers: ModelProviderResponse[];
  selections: ModelSelectionResponse[];
}

const EMPTY_PROVIDERS: ModelProviderResponse[] = [];
const EMPTY_SELECTIONS: ModelSelectionResponse[] = [];

export default function ProvidersPage() {
  const { t } = useTranslation();
  const { data, loading, error, refetch } = useAsyncData<ModelConfigData>(
    async () => {
      const [providers, selections] = await Promise.all([
        modelProvidersApi.list(),
        modelSelectionsApi.list(),
      ]);
      return { providers, selections };
    },
  );
  const { addToast } = useToast();
  const providers = data?.providers ?? EMPTY_PROVIDERS;
  const selections = data?.selections ?? EMPTY_SELECTIONS;

  const [selectedProviderName, setSelectedProviderName] = useState<
    string | null
  >(null);
  useEffect(() => {
    setSelectedProviderName((current) => {
      if (current && providers.some((provider) => provider.name === current)) {
        return current;
      }
      return providers[0]?.name ?? null;
    });
  }, [providers]);

  const selectedProvider = providers.find(
    (provider) => provider.name === selectedProviderName,
  );
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
  const selectedProviderSelections = selectedProvider
    ? selectionsByProvider.get(selectedProvider.name) ?? EMPTY_SELECTIONS
    : EMPTY_SELECTIONS;

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
    async (formData: ModelProviderCreate | ModelProviderUpdate) => {
      setProviderSubmitting(true);
      try {
        if (editingProvider) {
          await modelProvidersApi.update(
            editingProvider.name,
            formData as ModelProviderUpdate,
          );
          addToast(t("settings.providerUpdated"), "success");
        } else {
          const createData = formData as ModelProviderCreate;
          await modelProvidersApi.create(createData);
          setSelectedProviderName(createData.name);
          setHighlightProvider(createData.name);
          addToast(t("settings.providerCreated"), "success");
          window.setTimeout(() => setHighlightProvider(null), 3000);
        }
        setProviderDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : t("settings.operationFailed");
        addToast(msg, "error");
      } finally {
        setProviderSubmitting(false);
      }
    },
    [editingProvider, refetch, addToast, t],
  );

  const handleSelectionSubmit = useCallback(
    async (formData: ModelSelectionCreate | ModelSelectionUpdate) => {
      setSelectionSubmitting(true);
      try {
        if (editingSelection) {
          await modelSelectionsApi.update(
            editingSelection.id,
            formData as ModelSelectionUpdate,
          );
          addToast(t("settings.selectionUpdated"), "success");
        } else {
          await modelSelectionsApi.create(formData as ModelSelectionCreate);
          addToast(t("settings.selectionCreated"), "success");
        }
        setSelectionDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : t("settings.operationFailed");
        addToast(msg, "error");
      } finally {
        setSelectionSubmitting(false);
      }
    },
    [editingSelection, refetch, addToast, t],
  );

  const handleProviderDelete = async () => {
    if (!confirmProviderDelete) return;
    const deletedName = confirmProviderDelete.name;
    const deletedIndex = providers.findIndex(
      (provider) => provider.name === deletedName,
    );
    const fallbackProvider =
      providers.find(
        (provider, index) => index > deletedIndex && provider.name !== deletedName,
      ) ??
      providers.find(
        (provider, index) => index < deletedIndex && provider.name !== deletedName,
      );

    setDeletingProvider(deletedName);
    try {
      await modelProvidersApi.delete(deletedName);
      if (selectedProviderName === deletedName) {
        setSelectedProviderName(fallbackProvider?.name ?? null);
      }
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
      <div className="space-y-4">
        <div className="flex justify-end">
          <Skeleton className="h-10 w-28 rounded-xl" />
        </div>
        <div className="grid gap-4 lg:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
          <Skeleton className="h-72 rounded-[20px]" />
          <Skeleton className="h-72 rounded-[20px]" />
        </div>
      </div>
    );
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
    <div className="space-y-5">
      <div className="flex justify-end">
        <Button onClick={handleProviderCreate}>{t("settings.addProvider")}</Button>
      </div>

      {providers.length === 0 ? (
        <div className="rounded-[20px] border-2 border-dashed border-border-default px-5 py-16 text-center">
          <p className="mb-3 text-sm text-text-muted">{t("settings.noProviders")}</p>
          <Button variant="secondary" onClick={handleProviderCreate}>
            {t("settings.createFirstProvider")}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
          <section aria-labelledby="settings-providers-title" className="min-w-0">
            <div className="mb-3 flex items-center justify-between gap-3 px-1">
              <h2
                id="settings-providers-title"
                className="text-sm font-semibold text-text-primary"
              >
                {t("settings.providersTitle")}
              </h2>
              <span className="text-xs text-text-muted">
                {t("settings.providerCount", {
                  count: formatLocaleNumber(providers.length),
                })}
              </span>
            </div>
            <div className="space-y-2">
              {providers.map((provider) => (
                <ProviderListItem
                  key={provider.name}
                  provider={provider}
                  modelCount={
                    selectionsByProvider.get(provider.name)?.length ?? 0
                  }
                  selected={selectedProviderName === provider.name}
                  deleting={deletingProvider === provider.name}
                  highlight={highlightProvider === provider.name}
                  onSelect={() => setSelectedProviderName(provider.name)}
                  onEdit={handleProviderEdit}
                  onDelete={setConfirmProviderDelete}
                />
              ))}
            </div>
          </section>

          {selectedProvider ? (
            <ProviderModelsPanel
              provider={selectedProvider}
              selections={selectedProviderSelections}
              deletingSelection={deletingSelection}
              onAddModel={() => handleSelectionCreate(selectedProvider.name)}
              onEditProvider={handleProviderEdit}
              onDeleteProvider={setConfirmProviderDelete}
              onEditSelection={handleSelectionEdit}
              onDeleteSelection={setConfirmSelectionDelete}
            />
          ) : null}
        </div>
      )}

      <FormDrawer
        open={providerDrawerOpen}
        title={
          editingProvider
            ? t("settings.editProvider")
            : t("settings.addProviderTitle")
        }
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
        title={
          editingSelection
            ? t("settings.editSelection")
            : t("settings.addSelection")
        }
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
  );
}

function ProviderListItem({
  provider,
  modelCount,
  selected,
  deleting,
  highlight,
  onSelect,
  onEdit,
  onDelete,
}: {
  provider: ModelProviderResponse;
  modelCount: number;
  selected: boolean;
  deleting: boolean;
  highlight: boolean;
  onSelect: () => void;
  onEdit: (provider: ModelProviderResponse) => void;
  onDelete: (provider: ModelProviderResponse) => void;
}) {
  const { t } = useTranslation();

  return (
    <Card
      padding="sm"
      shadow="none"
      className={`transition-all duration-300 ${
        selected
          ? "border-primary-500 bg-primary-50/60 ring-1 ring-primary-500/20"
          : "hover:border-border-default hover:bg-surface-secondary/40"
      } ${highlight ? "ring-2 ring-primary-500 shadow-brand-glow" : ""}`}
    >
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className="w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40"
      >
        <div className="flex items-start justify-between gap-2">
          <h3 className="min-w-0 truncate text-sm font-semibold text-text-primary">
            {provider.name}
          </h3>
          <Badge
            variant={provider.has_api_key ? "success" : "warning"}
            size="sm"
          >
            {provider.has_api_key
              ? t("settings.configuredKey")
              : t("settings.unconfiguredKey")}
          </Badge>
        </div>
        <p className="mt-1 truncate text-xs text-text-secondary">
          {provider.provider}
        </p>
        <p className="mt-2 text-xs text-text-muted">
          {t("settings.modelCount", {
            count: formatLocaleNumber(modelCount),
          })}
        </p>
      </button>
      <div className="mt-3 flex justify-end gap-1 border-t border-border-light pt-2">
        <Button variant="ghost" size="sm" onClick={() => onEdit(provider)}>
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
    </Card>
  );
}

function ProviderModelsPanel({
  provider,
  selections,
  deletingSelection,
  onAddModel,
  onEditProvider,
  onDeleteProvider,
  onEditSelection,
  onDeleteSelection,
}: {
  provider: ModelProviderResponse;
  selections: ModelSelectionResponse[];
  deletingSelection: number | null;
  onAddModel: () => void;
  onEditProvider: (provider: ModelProviderResponse) => void;
  onDeleteProvider: (provider: ModelProviderResponse) => void;
  onEditSelection: (selection: ModelSelectionResponse) => void;
  onDeleteSelection: (selection: ModelSelectionResponse) => void;
}) {
  const { t } = useTranslation();
  const shouldShowBaseUrl =
    provider.provider === "OpenAI Compatible" && !!provider.base_url;

  return (
    <Card className="min-w-0" padding="lg">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate font-display text-lg font-semibold text-text-primary">
              {provider.name}
            </h2>
            <Badge
              variant={provider.has_api_key ? "success" : "warning"}
              size="sm"
            >
              {provider.has_api_key
                ? t("settings.configuredKey")
                : t("settings.unconfiguredKey")}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-text-secondary">{provider.provider}</p>
          {shouldShowBaseUrl ? (
            <p className="mt-1 truncate font-mono text-xs text-text-muted">
              {provider.base_url}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-1">
          <Button variant="secondary" size="sm" onClick={onAddModel}>
            {t("settings.addModel")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onEditProvider(provider)}
          >
            {t("settings.edit")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDeleteProvider(provider)}
            className="text-error-text hover:bg-error-bg"
          >
            {t("settings.delete")}
          </Button>
        </div>
      </div>

      <div className="mt-5 border-t border-border-light pt-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-text-primary">
            {t("settings.modelSelections")}
          </h3>
          <span className="text-xs text-text-muted">
            {t("settings.modelCount", {
              count: formatLocaleNumber(selections.length),
            })}
          </span>
        </div>

        {selections.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-default px-4 py-8 text-center">
            <p className="mb-3 text-sm text-text-muted">
              {t("settings.noProviderModels")}
            </p>
            <Button variant="secondary" size="sm" onClick={onAddModel}>
              {t("settings.addModel")}
            </Button>
          </div>
        ) : (
          <div className="space-y-2">
            {selections.map((selection) => (
              <div
                key={selection.id}
                className="group/model-row rounded-xl border border-border-light bg-surface-secondary/60 px-4 py-3"
              >
                <div className="flex min-h-8 flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="break-all text-sm font-medium text-text-primary">
                        {selection.model_name}
                      </h4>
                      <ModelCapabilityIcon
                        supportsImage={selection.supports_image_input}
                      />
                      {selection.provider.has_api_key ? null : (
                        <Badge variant="warning" size="sm">
                          {t("settings.missingKey")}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover/model-row:opacity-100 sm:group-focus-within/model-row:opacity-100">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onEditSelection(selection)}
                    >
                      {t("settings.edit")}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteSelection(selection)}
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
    </Card>
  );
}

function ModelCapabilityIcon({ supportsImage }: { supportsImage: boolean }) {
  const { t } = useTranslation();
  const label = supportsImage
    ? t("settings.imageSupported")
    : t("settings.textOnly");
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
