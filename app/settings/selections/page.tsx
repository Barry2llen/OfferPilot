"use client";

import { useState, useCallback } from "react";
import { modelSelectionsApi } from "@/app/lib/api/model-selections";
import { useAsyncData } from "@/app/hooks/use-async-data";
import { useAppActions } from "@/app/lib/context/app-context";
import { useToast } from "@/app/components/ui/toast";
import SelectionCard from "@/app/components/settings/selection-card";
import SelectionForm from "@/app/components/settings/selection-form";
import FormDrawer from "@/app/components/ui/form-drawer";
import ConfirmDialog from "@/app/components/ui/confirm-dialog";
import Button from "@/app/components/ui/button";
import Spinner from "@/app/components/ui/spinner";
import type {
  ModelSelectionResponse,
  ModelSelectionCreate,
} from "@/app/lib/api/types";

export default function SelectionsPage() {
  const { data: selections, loading, error, refetch } = useAsyncData(
    () => modelSelectionsApi.list()
  );

  const { setModelSelection } = useAppActions();
  const { addToast } = useToast();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<ModelSelectionResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] =
    useState<ModelSelectionResponse | null>(null);

  const handleCreate = () => {
    setEditing(null);
    setDrawerOpen(true);
  };

  const handleEdit = (s: ModelSelectionResponse) => {
    setEditing(s);
    setDrawerOpen(true);
  };

  const handleSubmit = useCallback(
    async (data: ModelSelectionCreate) => {
      setSubmitting(true);
      try {
        if (editing) {
          await modelSelectionsApi.update(editing.id, data);
          addToast("模型选择已更新", "success");
        } else {
          await modelSelectionsApi.create(data);
          addToast("模型选择已创建", "success");
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
    setDeleting(confirmDelete.id);
    try {
      await modelSelectionsApi.delete(confirmDelete.id);
      addToast("模型选择已删除", "success");
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
            模型选择
          </h1>
          <p className="text-sm text-text-muted mt-1">
            选择要在 AI 对话中使用的模型
          </p>
        </div>
        <Button onClick={handleCreate}>添加模型</Button>
      </div>

      {selections && selections.length === 0 ? (
        <div className="text-center py-16 border-2 border-dashed border-border-default rounded-[20px]">
          <p className="text-text-muted text-sm mb-3">
            暂无模型选择配置，请先创建模型供应商
          </p>
          <a href="/settings/providers">
            <Button variant="secondary">前往模型供应商</Button>
          </a>
        </div>
      ) : (
        <div className="space-y-3">
          {selections?.map((s) => (
            <SelectionCard
              key={s.id}
              selection={s}
              onEdit={handleEdit}
              onDelete={setConfirmDelete}
              deleting={deleting === s.id}
            />
          ))}
        </div>
      )}

      <FormDrawer
        open={drawerOpen}
        title={editing ? "编辑模型选择" : "添加模型选择"}
        onClose={() => setDrawerOpen(false)}
      >
        <SelectionForm
          initial={editing ?? undefined}
          onSubmit={handleSubmit}
          onCancel={() => setDrawerOpen(false)}
          submitting={submitting}
        />
      </FormDrawer>

      <ConfirmDialog
        open={!!confirmDelete}
        title="删除模型选择"
        message={`确定要删除「${confirmDelete?.provider.name} / ${confirmDelete?.model_name}」吗？`}
        confirmLabel="删除"
        variant="danger"
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
        loading={!!deleting}
      />
    </div>
  );
}
