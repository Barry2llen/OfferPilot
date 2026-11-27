const MAX_PREVIEW_INPUT_LENGTH = 2048;

/** Collapses Markdown syntax in model replies so previews read as plain text. */
export function plainPreview(value: string | null | undefined): string {
  if (!value) return "";
  return value.trimStart().slice(0, MAX_PREVIEW_INPUT_LENGTH)
    .replace(/```[\w-]*/g, " ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^[ \t]*(?:#{1,6}[ \t]+|>[ \t]?|[-*+][ \t]+|\d+[.)][ \t]+)/gm, "")
    .replace(/^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$/gm, " ")
    .replace(/^[ \t]*(?:\|[ \t]*)?:?-{3,}:?(?:[ \t]*\|[ \t]*:?-{3,}:?)*[ \t]*(?:\|[ \t]*)?$/gm, " ")
    .replace(/\|/g, " ")
    .replace(/(\*\*|__|`|~~)/g, "")
    .replace(/(^|\s)#{1,6}(?=\s)/g, "$1")
    .replace(/(^|\s)-{3,}(?=\s|$)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
