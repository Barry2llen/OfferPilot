import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { AnimatePresence, motion } from "motion/react";
import type { ToolCallEntry } from "@/app/hooks/use-chat-stream";
import i18n, { formatLocaleNumber } from "@/app/lib/i18n";

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

interface QueryToolOutput {
  question: string;
  choice: string;
  note: string | null;
  firstChoice?: string;
  firstChoiceDescription?: string;
  secondChoice?: string;
  secondChoiceDescription?: string;
  thirdChoice?: string;
  thirdChoiceDescription?: string;
}

const statusLabelKeys: Record<ToolStatus, string> = {
  running: "chat.toolRunning",
  success: "",
  error: "chat.toolFailed",
};

const statusClassNames: Record<ToolStatus, string> = {
  running: "text-info-text",
  success: "text-success-text",
  error: "text-error-text",
};

const dotClassNames: Record<ToolStatus, string> = {
  running: "bg-info-text animate-pulse",
  success: "bg-success-text",
  error: "bg-error-text",
};

const searchToolNames = new Set(["web_search", "web_search_exa", "find_similar_exa"]);
const fetchToolNames = new Set(["web_fetch", "web_fetch_exa"]);

export default function ToolCallCard({
  entry,
  defaultExpanded = false,
}: ToolCallCardProps) {
  useTranslation();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isWebTool = isWebResultTool(entry.name);
  const isQuery = isQueryTool(entry.name);
  const canExpand = hasToolDetails(entry);
  const searchResults = useMemo(
    () => getSearchResults(entry.name, entry.output),
    [entry.name, entry.output]
  );
  const showSearchEmpty =
    isWebTool &&
    entry.status === "success" &&
    entry.output !== undefined &&
    searchResults.length === 0;
  const summary = buildSummary(entry, searchResults, showSearchEmpty);
  const statusLabel = getStatusLabel(entry);
  const toolDisplayName = getToolDisplayName(entry);

  return (
    <div className="py-1">
      <div
        className={`mx-auto w-full max-w-3xl rounded-xl border bg-white/60 ${
          entry.status === "error" ? "border-error-text/25" : "border-border-default"
        }`}
      >
        <button
          type="button"
          onClick={canExpand ? () => setExpanded((value) => !value) : undefined}
          disabled={!canExpand}
          className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-text-secondary transition-colors ${
            canExpand ? "hover:bg-surface-secondary/45" : "cursor-default"
          }`}
          aria-expanded={canExpand ? expanded : undefined}
        >
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${dotClassNames[entry.status]}`}
          />
          <ToolIcon name={entry.name} className="w-4 h-4 text-text-secondary shrink-0" />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <span className="truncate text-sm font-medium text-text-secondary">
                {toolDisplayName}
              </span>
              {statusLabel && (
                <span
                  className={`shrink-0 text-[11px] font-medium ${
                    statusClassNames[entry.status]
                  }`}
                >
                  {statusLabel}
                </span>
              )}
            </span>
            {summary && (
              <span className="mt-0.5 block truncate text-xs text-text-muted">
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

        <AnimatePresence>
          {canExpand && expanded && (
            <motion.div
              className="overflow-hidden border-t border-border-default px-3 py-2"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeInOut" }}
            >
              {isQuery ? (
                <QueryToolDetails entry={entry} />
              ) : isWebTool && searchResults.length > 0 ? (
                <SearchResultList results={searchResults} />
              ) : showSearchEmpty ? (
                <SearchEmptyState output={entry.output} />
              ) : (
                <ToolRawDetails entry={entry} />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function QueryToolDetails({ entry }: { entry: ToolCallEntry }) {
  const question = getQueryQuestion(entry);
  const answer = getQueryAnswer(entry);

  return (
    <div className="space-y-2 text-xs leading-relaxed text-text-secondary">
      <DetailBlock label={i18n.t("chat.question")} value={question || i18n.t("chat.noQuestion")} />
      {entry.status === "success" && (
        <DetailBlock label={i18n.t("chat.answer")} value={answer || i18n.t("chat.noAnswer")} />
      )}
      {entry.status === "running" && (
        <DetailBlock label={i18n.t("chat.status")} value={i18n.t("chat.waitingUserDecision")} />
      )}
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
        <span className="text-text-muted">{i18n.t("chat.noToolDetails")}</span>
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

function getToolDisplayName(entry: ToolCallEntry): string {
  if (isQueryTool(entry.name) && entry.status === "success") {
    return i18n.t("chat.askedQuestion");
  }
  if (isSearchTool(entry.name)) {
    return i18n.t("chat.webSearch");
  }
  if (isFetchTool(entry.name)) {
    return i18n.t("chat.webRead");
  }
  return entry.name || i18n.t("chat.unknownTool");
}

function getStatusLabel(entry: ToolCallEntry): string {
  if (isQueryTool(entry.name) && entry.status === "running") {
    return i18n.t("chat.waitingDecision");
  }
  const key = statusLabelKeys[entry.status];
  return key ? i18n.t(key) : "";
}

function ToolIcon({ name, className }: { name: string, className?: string }) {
  if (isQueryTool(name)) {
    return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 18h.01" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.09 9a3 3 0 115.82 1c-.7 1.2-1.91 1.63-2.47 2.25-.36.4-.44.82-.44 1.75" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    );
  }
  if (isSearchTool(name)) {
    return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    );
  }
  if (isFetchTool(name)) {
    return (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
    );
  }
  return (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}

function buildSummary(
  entry: ToolCallEntry,
  searchResults: SearchResult[],
  showSearchEmpty: boolean
): string {
  if (isQueryTool(entry.name)) {
    return getQueryQuestion(entry) || i18n.t("chat.waitingUserDecision");
  }
  if (entry.status === "running") {
    const query = getInputText(entry.input);
    return query
      ? i18n.t("chat.parameter", { value: query })
      : i18n.t("chat.toolWorking");
  }
  if (entry.error) {
    return entry.error;
  }
  if (searchResults.length > 0) {
    return isFetchTool(entry.name)
      ? i18n.t("chat.webResults", {
          count: formatLocaleNumber(searchResults.length),
        })
      : i18n.t("chat.searchResults", {
          count: formatLocaleNumber(searchResults.length),
        });
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
    if (Array.isArray(item.results)) {
      return searchResultsFromArray(item.results);
    }
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

  return searchResultsFromArray(parsed);
}

function searchResultsFromArray(items: unknown[]): SearchResult[] {
  if (!items.some((item) => item && typeof item === "object" && "url" in item)) {
    return parseSearchResultText(extractTextBlocks(items));
  }

  return items.flatMap((item) => {
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

function isQueryTool(name: string): boolean {
  return name === "query";
}

function hasToolDetails(entry: ToolCallEntry): boolean {
  return entry.input !== undefined || entry.output !== undefined || Boolean(entry.error);
}

function getQueryQuestion(entry: ToolCallEntry): string {
  const output = parseQueryToolOutput(entry.output);
  if (output?.question) {
    return output.question;
  }
  const question = entry.input?.question;
  return typeof question === "string" ? question : "";
}

function getQueryAnswer(entry: ToolCallEntry): string {
  const output = parseQueryToolOutput(entry.output);
  if (!output) {
    return "";
  }
  if (output.choice === "other") {
    return output.note || i18n.t("chat.other");
  }

  const choiceText = getQueryChoiceText(entry.input, output.choice, output);
  if (!output.note) {
    return choiceText || output.choice;
  }
  return `${choiceText || output.choice} ${i18n.t("chat.note", { note: output.note })}`;
}

function getQueryChoiceText(
  input: Record<string, unknown> | undefined,
  choice: string,
  output?: QueryToolOutput | null
): string {
  const outputValue = output?.[choice as keyof QueryToolOutput];
  if (typeof outputValue === "string") {
    return outputValue;
  }
  const value = input?.[choice];
  return typeof value === "string" ? value : "";
}

function parseQueryToolOutput(output: unknown): QueryToolOutput | null {
  const parsed = parseMaybeJson(output);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return null;
  }

  const item = parsed as Record<string, unknown>;
  const choice = item.choice;
  if (typeof choice !== "string") {
    return null;
  }

  const question = item.question;
  const note = item.note;
  return {
    question: typeof question === "string" ? question : "",
    choice,
    note: typeof note === "string" ? note : null,
    firstChoice:
      typeof item.firstChoice === "string" ? item.firstChoice : undefined,
    firstChoiceDescription:
      typeof item.firstChoiceDescription === "string"
        ? item.firstChoiceDescription
        : undefined,
    secondChoice:
      typeof item.secondChoice === "string" ? item.secondChoice : undefined,
    secondChoiceDescription:
      typeof item.secondChoiceDescription === "string"
        ? item.secondChoiceDescription
        : undefined,
    thirdChoice:
      typeof item.thirdChoice === "string" ? item.thirdChoice : undefined,
    thirdChoiceDescription:
      typeof item.thirdChoiceDescription === "string"
        ? item.thirdChoiceDescription
        : undefined,
  };
}

function getSearchEmptyMessage(output: unknown): string {
  const parsed = parseMaybeJson(output);
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const message = (parsed as Record<string, unknown>).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return i18n.t("chat.searchEmpty");
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
