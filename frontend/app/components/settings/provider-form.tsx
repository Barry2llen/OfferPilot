"use client";

import { useState } from "react";
import Button from "@/app/components/ui/button";
import type {
  Provider,
  ModelProviderCreate,
  ModelProviderResponse,
  ModelProviderUpdate,
} from "@/app/lib/api/types";

interface ProviderFormProps {
  initial?: ModelProviderResponse;
  onSubmit: (data: ModelProviderCreate | ModelProviderUpdate) => Promise<void>;
  onCancel: () => void;
  submitting: boolean;
}

const providerOptions: { value: Provider; label: string }[] = [
  { value: "OpenAI", label: "OpenAI" },
  { value: "Google", label: "Google" },
  { value: "Anthropic", label: "Anthropic" },
  { value: "DeepSeek", label: "DeepSeek" },
  { value: "OpenAI Compatible", label: "OpenAI Compatible" },
];

export default function ProviderForm({
  initial,
  onSubmit,
  onCancel,
  submitting,
}: ProviderFormProps) {
  const [provider, setProvider] = useState<Provider>(
    (initial?.provider as Provider) || "OpenAI"
  );
  const [name, setName] = useState(initial?.name || "");
  const [baseUrl, setBaseUrl] = useState(initial?.base_url || "");
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);

  const isEdit = !!initial;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const data: ModelProviderCreate | ModelProviderUpdate = isEdit
      ? {
          provider,
          base_url: baseUrl || null,
        }
      : {
          provider,
          name,
        };

    if (!isEdit && baseUrl) {
      data.base_url = baseUrl;
    }

    if (isEdit) {
      if (clearKey) {
        data.api_key = null;
      } else if (apiKey) {
        data.api_key = apiKey;
      }
    } else if (apiKey) {
      data.api_key = apiKey;
    }

    await onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          供应商类型
        </label>
        <select
          value={provider}
          onChange={(e) => setProvider(e.target.value as Provider)}
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 disabled:opacity-50 disabled:bg-surface-secondary"
        >
          {providerOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          配置名称
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="如: default-openai"
          disabled={isEdit}
          required
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40 disabled:opacity-50 disabled:bg-surface-secondary"
        />
        <p className="text-xs text-text-muted mt-1">
          配置名称会作为模型选择的引用键，创建后不可修改
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          Base URL
          <span className="text-text-muted font-normal ml-1">(可选)</span>
        </label>
        <input
          type="url"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://api.example.com/v1"
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
        <p className="text-xs text-text-muted mt-1">
          OpenAI Compatible 通常需要配置
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1.5">
          API Key
          <span className="text-text-muted font-normal ml-1">
            {isEdit ? "(留空保持不变)" : "(可选)"}
          </span>
        </label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => {
            setApiKey(e.target.value);
            if (e.target.value) {
              setClearKey(false);
            }
          }}
          placeholder={isEdit ? "输入新密钥以更新" : "sk-..."}
          autoComplete="off"
          className="w-full rounded-xl border border-border-default px-3.5 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500/40"
        />
        {isEdit && (
          <label className="flex items-center gap-2 mt-2 cursor-pointer">
            <input
              type="checkbox"
              checked={clearKey}
              onChange={(e) => setClearKey(e.target.checked)}
              disabled={!!apiKey}
              className="rounded"
            />
            <span className="text-xs text-text-muted">清空已配置的 API Key</span>
          </label>
        )}
      </div>

      <div className="flex gap-3 pt-2">
        <Button type="submit" disabled={submitting || !name} className="flex-1">
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
