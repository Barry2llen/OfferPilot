"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import { modelProvidersApi } from "@/app/lib/api/model-providers";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useToast } from "@/app/components/ui/toast";
import ProviderCard from "@/app/components/settings/provider-card";
import ProviderForm from "@/app/components/settings/provider-form";
import FormDrawer from "@/app/components/ui/form-drawer";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Button from "@/app/components/ui/button";
import Badge from "@/app/components/ui/badge";
import Spinner from "@/app/components/ui/spinner";
import type {
  ModelProviderResponse,
  ModelProviderCreate,
} from "@/app/lib/api/types";

export default function ProvidersPage() {
  const { data: providers, loading, error, refetch } = useAsyncData(
    () => modelProvidersApi.list()
  );

  const { addToast } = useToast();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<ModelProviderResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] =
    useState<ModelProviderResponse | null>(null);

  const handleCreate = () => {
    setEditing(null);
    setDrawerOpen(true);
  };

  const handleEdit = (p: ModelProviderResponse) => {
    setEditing(p);
    setDrawerOpen(true);
  };

  const handleSubmit = useCallback(
    async (data: ModelProviderCreate) => {
      setSubmitting(true);
      try {
        if (editing) {
          await modelProvidersApi.update(editing.name, data);
          addToast("供应商配置已更新", "success");
        } else {
          await modelProvidersApi.create(data);
          addToast("供应商配置已创建", "success");
        }
        setDrawerOpen(false);
        refetch();
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "操作失败";
        addToast(msg, "error");
      } finally {
        setSubmitting(false);
      }
    },
    [editing, refetch, addToast]
  );

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setDeleting(confirmDelete.name);
    try {
      await modelProvidersApi.delete(confirmDelete.name);
      addToast("供应商已删除", "success");
      setConfirmDelete(null);
      refetch();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "删除失败";
      addToast(msg, "error");
    } finally {
      setDeleting(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto p-6">
        <div className="flex items-center justify-center py-20">
          <Spinner size="lg" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto p-6">
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
    <div className="max-w-2xl mx-auto p-6 lg:py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary">
            模型供应商
          </h1>
          <p className="text-sm text-text-muted mt-1">
            管理 AI 模型的供应商配置和 API 密钥
          </p>
        </div>
        <Button onClick={handleCreate}>添加供应商</Button>
      </div>

      {providers && providers.length === 0 ? (
        <div className="text-center py-16 border-2 border-dashed border-border-default rounded-[20px]">
          <p className="text-text-muted text-sm mb-3">暂无模型供应商配置</p>
          <Button variant="secondary" onClick={handleCreate}>
            创建第一个供应商
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {providers?.map((p) => (
            <ProviderCard
              key={p.name}
              provider={p}
              onEdit={handleEdit}
              onDelete={setConfirmDelete}
              deleting={deleting === p.name}
            />
          ))}
        </div>
      )}

      <FormDrawer
        open={drawerOpen}
        title={editing ? "编辑供应商" : "添加供应商"}
        onClose={() => setDrawerOpen(false)}
      >
        <ProviderForm
          initial={editing ?? undefined}
          onSubmit={handleSubmit}
          onCancel={() => setDrawerOpen(false)}
          submitting={submitting}
        />
      </FormDrawer>

      <ConfirmDialog
        open={!!confirmDelete}
        title="删除供应商配置"
        message={`确定要删除「${confirmDelete?.name}」吗？如果该供应商仍有模型选择引用，删除将失败。`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
        loading={!!deleting}
      />
    </div>
  );
}
