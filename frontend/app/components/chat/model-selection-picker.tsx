"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Button from "@/app/components/ui/button";
import type { ModelSelectionResponse } from "@/app/lib/api/types";

interface ModelSelectionPickerProps {
  models: ModelSelectionResponse[];
  loading: boolean;
  value: number | null;
  disabled?: boolean;
  onChange: (id: number | null) => void;
}

interface ProviderGroup {
  provider: string;
  items: ModelSelectionResponse[];
}

const providerStyles: Record<string, string> = {
  DeepSeek: "bg-info-bg text-info-text",
  Google: "bg-success-bg text-success-text",
  OpenAI: "bg-text-charcoal text-white",
  Anthropic: "bg-warning-bg text-warning-text",
  "OpenAI Compatible": "bg-surface-secondary text-text-secondary",
};

function modelLabel(model: ModelSelectionResponse): string {
  return `${model.provider.provider} / ${model.model_name}`;
}

function providerClass(provider: string): string {
  return providerStyles[provider] ?? "bg-surface-secondary text-text-secondary";
}

function groupModels(
  models: ModelSelectionResponse[],
  query: string
): ProviderGroup[] {
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = normalizedQuery
    ? models.filter((model) =>
        [
          model.provider.provider,
          model.provider.name,
          model.model_name,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery)
      )
    : models;

  const groups = new Map<string, ModelSelectionResponse[]>();
  for (const model of filtered) {
    const provider = model.provider.provider || "其他";
    groups.set(provider, [...(groups.get(provider) ?? []), model]);
  }

  return Array.from(groups.entries()).map(([provider, items]) => ({
    provider,
    items,
  }));
}

function EmptyState({
  loading,
  query,
}: {
  loading: boolean;
  query: string;
}) {
  return (
    <div className="px-4 py-8 text-center text-sm text-text-muted">
      {loading
        ? "正在加载模型..."
        : query
          ? "没有匹配的模型"
          : "暂无可用模型"}
    </div>
  );
}

function SelectionList({
  groups,
  selectedId,
  query,
  loading,
  onSelect,
}: {
  groups: ProviderGroup[];
  selectedId: number | null;
  query: string;
  loading: boolean;
  onSelect: (id: number | null) => void;
}) {
  if (groups.length === 0) {
    return <EmptyState loading={loading} query={query} />;
  }

  return (
    <div className="space-y-4">
      {!query && (
        <button
          type="button"
          onClick={() => onSelect(null)}
          className={`flex w-full items-center justify-between rounded-xl px-3 py-2.5 text-left text-sm transition ${
            selectedId === null
              ? "bg-info-bg text-info-text"
              : "text-text-secondary hover:bg-surface-secondary"
          }`}
        >
          <span>未选择</span>
          {selectedId === null && (
            <span className="text-xs font-semibold">当前</span>
          )}
        </button>
      )}

      {groups.map((group) => (
        <section key={group.provider} className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${providerClass(group.provider)}`}
              >
                {group.provider}
              </span>
              <span className="text-[11px] text-text-muted">
                {group.items.length} 个模型
              </span>
            </div>
          </div>

          <div className="space-y-1">
            {group.items.map((model) => {
              const selected = model.id === selectedId;
              return (
                <button
                  key={model.id}
                  type="button"
                  onClick={() => onSelect(model.id)}
                  className={`group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                    selected
                      ? "bg-text-charcoal text-white shadow-sm"
                      : "hover:bg-surface-secondary"
                  }`}
                >
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                      selected
                        ? "bg-white/15 text-white"
                        : providerClass(group.provider)
                    }`}
                  >
                    {group.provider.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">
                      {model.model_name}
                    </span>
                    <span
                      className={`block truncate text-xs ${
                        selected ? "text-white/65" : "text-text-muted"
                      }`}
                    >
                      {model.provider.name}
                      {model.supports_image_input ? " · 支持图片输入" : ""}
                    </span>
                  </span>
                  {selected && (
                    <span className="shrink-0 text-xs font-semibold">
                      当前
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

export default function ModelSelectionPicker({
  models,
  loading,
  value,
  disabled = false,
  onChange,
}: ModelSelectionPickerProps) {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  const selected = useMemo(
    () => models.find((model) => model.id === value) ?? null,
    [models, value]
  );
  const groups = useMemo(() => groupModels(models, query), [models, query]);
  const isDisabled = disabled || loading || models.length === 0;

  useEffect(() => {
    if (!open && !expanded) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (open && !rootRef.current?.contains(event.target as Node)) {
        setQuery("");
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setQuery("");
        setOpen(false);
        setExpanded(false);
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [expanded, open]);

  const handleSelect = (id: number | null) => {
    onChange(id);
    setQuery("");
    setOpen(false);
    setExpanded(false);
  };

  const renderPickerContent = (listClassName: string) => (
    <>
      <div className="relative">
        <svg
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M21 21l-4.35-4.35m1.1-5.15a6.25 6.25 0 11-12.5 0 6.25 6.25 0 0112.5 0z"
          />
        </svg>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索 provider、供应商或模型"
          className="h-10 w-full rounded-xl bg-surface-secondary pl-9 pr-3 text-sm text-text-primary outline-none transition focus:bg-white focus:ring-2 focus:ring-primary-500/25"
        />
      </div>
      <div className={listClassName}>
        <SelectionList
          groups={groups}
          selectedId={value}
          query={query}
          loading={loading}
          onSelect={handleSelect}
        />
      </div>
    </>
  );

  return (
    <div ref={rootRef} className="relative flex min-w-0 items-center gap-2">
      <span className="shrink-0 text-xs text-text-muted">模型</span>
      <button
        type="button"
        onClick={() => {
          if (!isDisabled) {
            if (open) setQuery("");
            setOpen(!open);
          }
        }}
        disabled={isDisabled}
        className="flex h-9 w-60 max-w-[52vw] items-center gap-2 rounded-full bg-surface-secondary px-4 text-left text-sm text-text-primary shadow-sm outline-none transition hover:bg-border-light focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-primary-500/25 disabled:cursor-not-allowed disabled:text-text-muted disabled:shadow-none"
      >
        <span className="min-w-0 flex-1 truncate">
          {loading
            ? "加载中..."
            : selected
              ? modelLabel(selected)
              : models.length === 0
                ? "暂无可用模型"
                : "未选择"}
        </span>
        <svg
          className={`h-4 w-4 shrink-0 text-text-muted transition ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </button>

      {open && (
        <div className="absolute right-0 top-[calc(100%+0.5rem)] z-50 w-[26rem] max-w-[calc(100vw-2rem)] rounded-2xl bg-white p-3 shadow-[0_18px_50px_rgba(15,23,42,0.18)] ring-1 ring-black/5">
          {renderPickerContent("mt-4 max-h-[22rem] overflow-y-auto pr-1")}
          <div className="mt-3 flex items-center justify-between border-t border-border-light pt-3">
            <span className="text-xs text-text-muted">
              共 {models.length} 个模型
            </span>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setExpanded(true);
                setOpen(false);
              }}
            >
              展开选择
            </Button>
          </div>
        </div>
      )}

      {expanded && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-black/20 backdrop-blur-sm"
            onClick={() => {
              setQuery("");
              setExpanded(false);
            }}
          />
          <div className="relative flex max-h-[86vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-[0_24px_70px_rgba(15,23,42,0.24)]">
            <div className="flex items-center justify-between border-b border-border-light px-5 py-4">
              <div>
                <h3 className="font-display text-lg font-semibold text-text-primary">
                  选择模型
                </h3>
                <p className="text-xs text-text-muted">
                  按 provider 分类浏览当前已配置的模型
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setExpanded(false);
                }}
                className="rounded-lg p-1.5 text-text-muted transition hover:bg-surface-secondary hover:text-text-primary"
                aria-label="关闭模型选择"
              >
                <svg
                  className="h-5 w-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-5">
              {renderPickerContent("mt-4 pr-1")}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
