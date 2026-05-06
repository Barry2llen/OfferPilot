"use client";

import { useMemo, useState } from "react";
import type { ToolCallEntry } from "@/app/hooks/use-chat-stream";

type ToolStatus = ToolCallEntry["status"];

interface ToolCallCardProps {
  entry: ToolCallEntry;
  defaultExpanded?: boolean;
}

interface SearchResult {
  url: string;
  title?: string;
  favicon?: string;
}

const statusLabels: Record<ToolStatus, string> = {
  running: "执行中",
  success: "已完成",
  error: "失败",
};

const statusClassNames: Record<ToolStatus, string> = {
  running: "border-info-text/20 bg-info-bg/45 text-info-text",
  success: "border-success-text/20 bg-success-bg/45 text-success-text",
  error: "border-error-text/20 bg-error-bg/45 text-error-text",
};

const dotClassNames: Record<ToolStatus, string> = {
  running: "bg-info-text animate-pulse",
  success: "bg-success-text",
  error: "bg-error-text",
};

const searchEmptyMessage = "未提取到可展示的搜索链接";
const searchToolNames = new Set(["web_search", "web_search_exa", "find_similar_exa"]);
const fetchToolNames = new Set(["web_fetch", "web_fetch_exa"]);

export default function ToolCallCard({
  entry,
  defaultExpanded = false,
}: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const canExpand = isWebResultTool(entry.name);
  const searchResults = useMemo(
    () => getSearchResults(entry.name, entry.output),
    [entry.name, entry.output]
  );
  const showSearchEmpty =
    canExpand &&
    entry.status === "success" &&
    entry.output !== undefined &&
    searchResults.length === 0;
  const summary = canExpand ? buildSummary(entry, searchResults, showSearchEmpty) : "";

  return (
    <div className="flex justify-start py-1.5">
      <div
        className={`w-full max-w-[min(82%,42rem)] rounded-lg border bg-white shadow-sm ${
          entry.status === "error" ? "border-error-text/25" : "border-border-light"
        }`}
      >
        <button
          type="button"
          onClick={canExpand ? () => setExpanded((value) => !value) : undefined}
          disabled={!canExpand}
          className={`flex w-full items-center gap-2 px-3 py-2 text-left ${
            canExpand ? "hover:bg-surface-secondary/55" : "cursor-default"
          }`}
          aria-expanded={canExpand ? expanded : undefined}
        >
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${dotClassNames[entry.status]}`}
          />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <span className="truncate text-xs font-semibold text-text-primary">
                {getToolDisplayName(entry.name)}
              </span>
              <span
                className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${
                  statusClassNames[entry.status]
                }`}
              >
                {statusLabels[entry.status]}
              </span>
            </span>
            {summary && (
              <span className="mt-0.5 block truncate text-[11px] text-text-muted">
                {summary}
              </span>
            )}
          </span>
          {canExpand && (
            <svg
              className={`h-3.5 w-3.5 shrink-0 text-text-muted transition-transform ${
                expanded ? "rotate-90" : ""
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          )}
        </button>

        {canExpand && expanded && (
          <div className="border-t border-border-light px-3 py-2">
            {searchResults.length > 0 ? (
              <SearchResultList results={searchResults} />
            ) : showSearchEmpty ? (
              <SearchEmptyState output={entry.output} />
            ) : (
              <ToolRawDetails entry={entry} />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolRawDetails({ entry }: { entry: ToolCallEntry }) {
  return (
    <div className="space-y-2 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-text-secondary">
      {entry.input !== undefined && (
        <DetailBlock label="input" value={formatUnknown(entry.input)} />
      )}
      {entry.output !== undefined && (
        <DetailBlock label="output" value={formatUnknown(entry.output)} />
      )}
      {entry.error && (
        <DetailBlock label="error" value={entry.error} tone="error" />
      )}
      {entry.input === undefined && entry.output === undefined && !entry.error && (
        <span className="text-text-muted">暂无工具详情</span>
      )}
    </div>
  );
}

function DetailBlock({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "error";
}) {
  return (
    <div>
      <span className="text-text-muted">{label}:</span>{" "}
      <span className={tone === "error" ? "text-error-text" : ""}>{value}</span>
    </div>
  );
}

function SearchResultList({ results }: { results: SearchResult[] }) {
  return (
    <div className="space-y-1.5">
      {results.map((result, index) => (
        <a
          key={`${result.url}-${index}`}
          href={result.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-2 rounded-lg border border-border-light bg-surface-primary px-2.5 py-2 text-xs transition-colors hover:border-primary-200 hover:bg-info-bg/35"
        >
          <Favicon src={result.favicon} />
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-text-primary">
              {result.title || result.url}
            </span>
            <span className="block truncate text-[11px] text-text-muted">
              {formatUrl(result.url)}
            </span>
          </span>
          <svg
            className="h-3.5 w-3.5 shrink-0 text-text-muted"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 17L17 7M8 7h9v9" />
          </svg>
        </a>
      ))}
    </div>
  );
}

function SearchEmptyState({ output }: { output: unknown }) {
  return (
    <div className="rounded-lg border border-border-light bg-surface-secondary/50 px-3 py-2 text-xs text-text-muted">
      {getSearchEmptyMessage(output)}
    </div>
  );
}

function Favicon({ src }: { src?: string }) {
  const safeSrc = getSafeImageUrl(src);

  if (!safeSrc) {
    return <DefaultSiteIcon />;
  }

  return (
    <span
      aria-hidden="true"
      className="h-5 w-5 shrink-0 rounded-sm bg-surface-secondary bg-cover bg-center"
      style={{ backgroundImage: `url(${JSON.stringify(safeSrc)})` }}
    />
  );
}

function DefaultSiteIcon() {
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-surface-secondary text-text-muted">
      <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3a9 9 0 100 18 9 9 0 000-18z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.6 9h16.8M3.6 15h16.8M12 3c2 2.2 3 5.2 3 9s-1 6.8-3 9M12 3c-2 2.2-3 5.2-3 9s1 6.8 3 9" />
      </svg>
    </span>
  );
}

function getToolDisplayName(name: string): string {
  if (isSearchTool(name)) {
    return "网页搜索";
  }
  if (isFetchTool(name)) {
    return "网页读取";
  }
  return name || "未知工具";
}

function buildSummary(
  entry: ToolCallEntry,
  searchResults: SearchResult[],
  showSearchEmpty: boolean
): string {
  if (entry.status === "running") {
    const query = getInputText(entry.input);
    return query ? `参数：${query}` : "工具正在执行";
  }
  if (entry.error) {
    return entry.error;
  }
  if (searchResults.length > 0) {
    return isFetchTool(entry.name)
      ? `${searchResults.length} 个网页结果`
      : `${searchResults.length} 个搜索结果`;
  }
  if (showSearchEmpty) {
    return getSearchEmptyMessage(entry.output);
  }
  if (entry.output !== undefined) {
    return truncate(formatUnknown(entry.output).replace(/\s+/g, " "), 80);
  }
  return "";
}

function getInputText(input?: Record<string, unknown>): string {
  if (!input) {
    return "";
  }
  const value = input.query ?? input.url ?? input.id;
  if (typeof value === "string") {
    return truncate(value, 80);
  }
  return truncate(formatUnknown(input).replace(/\s+/g, " "), 80);
}

function getSearchResults(toolName: string, output: unknown): SearchResult[] {
  if (!isWebResultTool(toolName)) {
    return [];
  }

  const parsed = parseMaybeJson(output);
  if (typeof parsed === "string") {
    return parseSearchResultText(parsed);
  }
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const item = parsed as Record<string, unknown>;
    if (typeof item.url === "string" && item.url) {
      return [
        {
          url: item.url,
          title: typeof item.title === "string" ? item.title : undefined,
          favicon: typeof item.favicon === "string" ? item.favicon : undefined,
        },
      ];
    }
    return parseSearchResultText(extractTextBlocks(parsed));
  }
  if (!Array.isArray(parsed)) {
    return [];
  }

  if (!parsed.some((item) => item && typeof item === "object" && "url" in item)) {
    return parseSearchResultText(extractTextBlocks(parsed));
  }

  return parsed.flatMap((item) => {
    if (!item || typeof item !== "object" || !("url" in item)) {
      return [];
    }
    const url = (item as Record<string, unknown>).url;
    if (typeof url !== "string" || !url) {
      return [];
    }
    const title = (item as Record<string, unknown>).title;
    const favicon = (item as Record<string, unknown>).favicon;
    return [
      {
        url,
        title: typeof title === "string" ? title : undefined,
        favicon: typeof favicon === "string" ? favicon : undefined,
      },
    ];
  });
}

function isSearchTool(name: string): boolean {
  return searchToolNames.has(name);
}

function isFetchTool(name: string): boolean {
  return fetchToolNames.has(name);
}

function isWebResultTool(name: string): boolean {
  return isSearchTool(name) || isFetchTool(name);
}

function getSearchEmptyMessage(output: unknown): string {
  const parsed = parseMaybeJson(output);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const message = (parsed as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return searchEmptyMessage;
}

function extractTextBlocks(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => extractTextBlocks(item))
      .filter(Boolean)
      .join("\n\n");
  }
  if (value && typeof value === "object") {
    const item = value as Record<string, unknown>;
    if (typeof item.text === "string") {
      return item.text;
    }
    if (item.content !== undefined) {
      return extractTextBlocks(item.content);
    }
  }
  return "";
}

function parseSearchResultText(value: string): SearchResult[] {
  const colonResults = value.split("\n\n").flatMap((block) => {
    const result: Partial<SearchResult> = {};

    for (const line of block.split("\n")) {
      const separatorIndex = line.indexOf(":");
      if (separatorIndex < 0) {
        continue;
      }

      const key = line.slice(0, separatorIndex).trim();
      const rawValue = line.slice(separatorIndex + 1).trim();
      if (!rawValue || rawValue === "None") {
        continue;
      }

      if (key === "URL") {
        result.url = rawValue;
      }
      if (key === "Title") {
        result.title = rawValue;
      }
      if (key === "Favicon") {
        result.favicon = rawValue;
      }
    }

    return result.url ? [result as SearchResult] : [];
  });

  return colonResults.length > 0 ? colonResults : parseReprSearchResultText(value);
}

function parseReprSearchResultText(value: string): SearchResult[] {
  return value.split(/(?=SearchResult\(|Result\()/).flatMap((block) => {
    const result: Partial<SearchResult> = {};
    const matches = block.matchAll(/\b(url|title|favicon)=['"]([^'"]+)['"]/gi);

    for (const match of matches) {
      const key = match[1]?.toLowerCase();
      const rawValue = match[2];
      if (!rawValue || rawValue === "None") {
        continue;
      }
      if (key === "url") {
        result.url = rawValue;
      }
      if (key === "title") {
        result.title = rawValue;
      }
      if (key === "favicon") {
        result.favicon = rawValue;
      }
    }

    return result.url ? [result as SearchResult] : [];
  });
}

function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== "string") {
    return value;
  }

  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function formatUnknown(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value == null) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.hostname}${url.pathname === "/" ? "" : url.pathname}`;
  } catch {
    return value;
  }
}

function getSafeImageUrl(value?: string): string {
  if (!value) {
    return "";
  }
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? value : "";
  } catch {
    return "";
  }
}

function truncate(value: string, limit: number): string {
  return value.length > limit ? `${value.slice(0, limit - 1)}...` : value;
}
