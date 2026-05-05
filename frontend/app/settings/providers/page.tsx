"use client";

import { useMemo, useState, useCallback } from "react";
import { modelProvidersApi } from "@/app/lib/api/model-providers";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ProviderCard from "@/app/components/settings/provider-card";
import ProviderForm from "@/app/components/settings/provider-form";
import SelectionForm from "@/app/components/settings/selection-form";
import FormDrawer from "@/app/components/ui/form-drawer";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Badge from "@/app/components/ui/badge";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
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
  const { data, loading, error, refetch } = useAsyncData<ModelConfigData>(
    async () => {
      const [providers, selections] = await Promise.all([
        modelProvidersApi.list(),
        modelSelectionsApi.list(),
      ]);
      return { providers, selections };
    }
  );

  const { addToast } = useToast();
  const providers = data?.providers ?? EMPTY_PROVIDERS;
  const selections = data?.selections ?? EMPTY_SELECTIONS;
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
  const [editingProvider, setEditingProvider] =
    useState<ModelProviderResponse | null>(null);
  const [editingSelection, setEditingSelection] =
    useState<ModelSelectionResponse | null>(null);
  const [defaultProviderName, setDefaultProviderName] = useState("");
  const [providerSubmitting, setProviderSubmitting] = useState(false);
  const [selectionSubmitting, setSelectionSubmitting] = useState(false);
  const [deletingProvider, setDeletingProvider] = useState<string | null>(null);
  const [deletingSelection, setDeletingSelection] = useState<number | null>(null);
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
    async (data: ModelProviderCreate | ModelProviderUpdate) => {
      setProviderSubmitting(true);
      try {
        if (editingProvider) {
          await modelProvidersApi.update(
            editingProvider.name,
            data as ModelProviderUpdate
          );
          addToast("供应商配置已更新", "success");
        } else {
          await modelProvidersApi.create(data as ModelProviderCreate);
          addToast("供应商配置已创建", "success");
        }
        setProviderDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "操作失败";
        addToast(msg, "error");
      } finally {
        setProviderSubmitting(false);
      }
    },
    [editingProvider, refetch, addToast]
  );

  const handleSelectionSubmit = useCallback(
    async (data: ModelSelectionCreate | ModelSelectionUpdate) => {
      setSelectionSubmitting(true);
      try {
        if (editingSelection) {
          await modelSelectionsApi.update(
            editingSelection.id,
            data as ModelSelectionUpdate
          );
          addToast("模型选择已更新", "success");
        } else {
          await modelSelectionsApi.create(data as ModelSelectionCreate);
          addToast("模型选择已创建", "success");
        }
        setSelectionDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "操作失败";
        addToast(msg, "error");
      } finally {
        setSelectionSubmitting(false);
      }
    },
    [editingSelection, refetch, addToast]
  );

  const handleProviderDelete = async () => {
    if (!confirmProviderDelete) return;
    setDeletingProvider(confirmProviderDelete.name);
    try {
      await modelProvidersApi.delete(confirmProviderDelete.name);
      addToast("供应商已删除", "success");
      setConfirmProviderDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败";
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
      addToast("模型选择已删除", "success");
      setConfirmSelectionDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败";
      addToast(msg, "error");
    } finally {
      setDeletingSelection(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <div className="text-center py-20">
          <p className="text-error-text text-sm mb-4">{error}</p>
          <Button variant="secondary" onClick={refetch}>
            重试
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6 lg:py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary">
            模型配置
          </h1>
          <p className="text-sm text-text-muted mt-1">
            按供应商管理 API 密钥、模型选择和多模态能力
          </p>
        </div>
        <Button onClick={handleProviderCreate}>添加供应商</Button>
      </div>

      {providers && providers.length === 0 ? (
        <div className="text-center py-16 border-2 border-dashed border-border-default rounded-[20px]">
          <p className="text-text-muted text-sm mb-3">暂无模型供应商配置</p>
          <Button variant="secondary" onClick={handleProviderCreate}>
            创建第一个供应商
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
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <h4 className="text-sm font-medium text-text-primary">
                    模型选择
                  </h4>
                  <span className="text-xs text-text-muted">
                    {providerSelections.length} 个模型
                  </span>
                </div>

                {providerSelections.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-border-default px-4 py-5 text-center">
                    <p className="text-sm text-text-muted mb-3">
                      暂无模型，请为该供应商添加模型选择
                    </p>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleSelectionCreate(provider.name)}
                    >
                      添加模型
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {providerSelections.map((selection) => (
                      <div
                        key={selection.id}
                        className="rounded-xl border border-border-light bg-surface-secondary/60 px-4 py-3"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h5 className="text-sm font-medium text-text-primary break-all">
                                {selection.model_name}
                              </h5>
                              <Badge variant="info" size="sm">
                                ID: {selection.id}
                              </Badge>
                              <Badge
                                variant={
                                  selection.supports_image_input
                                    ? "success"
                                    : "neutral"
                                }
                                size="sm"
                              >
                                {selection.supports_image_input
                                  ? "支持图片"
                                  : "仅文本"}
                              </Badge>
                              {selection.provider.has_api_key ? null : (
                                <Badge variant="warning" size="sm">
                                  供应商未配置密钥
                                </Badge>
                              )}
                            </div>
                            <p className="text-xs text-text-muted mt-1">
                              {selection.provider.name} ({selection.provider.provider})
                            </p>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleSelectionEdit(selection)}
                            >
                              编辑
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setConfirmSelectionDelete(selection)}
                              disabled={deletingSelection === selection.id}
                              className="text-error-text hover:bg-error-bg"
                            >
                              {deletingSelection === selection.id
                                ? "删除中..."
                                : "删除"}
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
        title={editingProvider ? "编辑供应商" : "添加供应商"}
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
        title={editingSelection ? "编辑模型选择" : "添加模型选择"}
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
        title="删除供应商配置"
        message={`确定要删除「${confirmProviderDelete?.name}」吗？如果该供应商仍有模型选择引用，删除将失败。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleProviderDelete}
        onCancel={() => setConfirmProviderDelete(null)}
        loading={!!deletingProvider}
      />

      <ConfirmDialog
        open={!!confirmSelectionDelete}
        title="删除模型选择"
        message={`确定要删除「${confirmSelectionDelete?.provider.name} / ${confirmSelectionDelete?.model_name}」吗？`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleSelectionDelete}
        onCancel={() => setConfirmSelectionDelete(null)}
        loading={!!deletingSelection}
      />
    </div>
  );
}
