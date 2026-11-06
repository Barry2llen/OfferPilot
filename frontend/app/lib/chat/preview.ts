/** Collapses Markdown syntax in model replies so previews read as plain text. */
export function plainPreview(value: string | null | undefined): string {
  if (!value) return "";
  return value
    .replace(/```[\w-]*/g, " ")
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d+[.)]\s+)/gm, "")
    .replace(/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/gm, " ")
    .replace(/\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?/g, " ")
    .replace(/\s*\|\s*/g, " ")
    .replace(/(\*\*|__|`|~~)/g, "")
    .replace(/(^|\s)#{1,6}(?=\s)/g, "$1")
    .replace(/(^|\s)-{3,}(?=\s|$)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}
