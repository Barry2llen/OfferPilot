"use client";

import { useState, useEffect } from "react";
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
          模型供应商
        </label>
        <select
          value={providerName}
          onChange={(e) => setProviderName(e.target.value)}
          required
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 disabled:opacity-50 disabled:bg-surface-secondary"
        >
          <option value="">选择供应商...</option>
          {providers.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name} ({p.provider}{" "}
              {p.has_api_key ? "✓ 已配置" : "✗ 未配置密钥"})
            </option>
          ))}
        </select>
        {providers.length === 0 && (
          <p className="text-xs text-warning-text mt-1">
            暂无可用供应商，请先创建模型供应商配置
          </p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          模型名称
        </label>
        <input
          type="text"
          value={modelName}
          onChange={(e) => setModelName(e.target.value)}
          placeholder="如: gpt-4o-mini"
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
              className="sr-only peer"
            />
            <div className="w-9 h-5 bg-border-default rounded-full peer-checked:bg-primary-500 transition-colors" />
            <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow-sm peer-checked:translate-x-4 transition-transform" />
          </div>
          <span className="text-sm font-medium text-text-primary">
            支持图片输入
          </span>
          <span className="text-xs text-text-muted">
            用于简历图片和多模态工作流
          </span>
        </label>
      </div>

      <div className="flex gap-3 pt-2">
        <Button
          type="submit"
          disabled={submitting || !providerName || !modelName}
          className="flex-1"
        >
          {submitting ? "保存中..." : isEdit ? "保存更改" : "创建"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={submitting}
          className="flex-1"
        >
          取消
        </Button>
      </div>
    </form>
  );
}
