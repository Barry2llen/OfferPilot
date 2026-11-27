import i18n from "@/app/lib/i18n";

type AnalysisLabelGroup = "factType" | "blockType" | "importance";

/** Turns a model-provided token such as `domain_knowledge` into readable text. */
export function humanizeToken(value: string): string {
  const text = value.trim().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

/**
 * Localizes known analysis enum values and keeps unknown model categories
 * readable instead of exposing raw snake_case tokens.
 */
export function analysisLabel(
  group: AnalysisLabelGroup,
  value: string | null | undefined,
): string {
  const raw = value?.trim() ?? "";
  if (!raw) return i18n.t("common.unknown");
  const key = `analysisLabels.${group}.${raw.toLowerCase()}`;
  return i18n.exists(key) ? i18n.t(key) : humanizeToken(raw);
}
