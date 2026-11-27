"""Describe the model content blocks written by chat attachment ingestion."""

from dataclasses import dataclass
from typing import TypedDict

from langchain_core.messages import HumanMessage

ATTACHMENT_LAYOUT_KEY = "_offerpilot_attachment_layout"
ATTACHMENT_LAYOUT_VERSION = 1


class AttachmentSpan(TypedDict):
    file_id: str
    injection_mode: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class AttachmentContent:
    prompt: str
    visible_block: dict
    blocks: list[str | dict]
    spans: list[AttachmentSpan]

    def payload(self, span: AttachmentSpan) -> list[str | dict]:
        return self.blocks[span["start"] : span["end"]]


def visible_attachment_prompt(prompt: str, reference_lines: list[str]) -> str:
    references = "\n".join(reference_lines)
    return f"{prompt or '请分析这些附件内容。'}\n\n[附件引用]\n{references}"


def attachment_content(message: HumanMessage) -> AttachmentContent | None:
    """Use a server-written layout only when it accounts for every content block."""
    metadata = message.additional_kwargs
    layout = metadata.get(ATTACHMENT_LAYOUT_KEY)
    blocks = message.content
    prompt = metadata.get("display_content")
    refs = metadata.get("attachments")
    if (
        not isinstance(layout, dict)
        or layout.get("version") != ATTACHMENT_LAYOUT_VERSION
        or not isinstance(blocks, list)
        or not blocks
        or not isinstance(prompt, str)
        or not isinstance(refs, list)
        or not refs
        or not isinstance(layout.get("spans"), list)
    ):
        return None

    identities: set[tuple[str, str]] = set()
    lines: list[str] = []
    for ref in refs:
        if not isinstance(ref, dict):
            return None
        file_id = ref.get("file_id")
        filename = ref.get("original_filename")
        mode = ref.get("injection_mode")
        if (
            not isinstance(file_id, str)
            or not isinstance(filename, str)
            or mode not in ("text", "ocr_text", "image")
        ):
            return None
        identities.add((file_id, mode))
        lines.append(f"- {file_id} ({filename}, mode={mode})")

    visible_block = blocks[0]
    if not isinstance(visible_block, dict) or visible_block != {
        "type": "text",
        "text": visible_attachment_prompt(prompt, lines),
    }:
        return None

    cursor = 1
    spans: list[AttachmentSpan] = []
    for span in layout["spans"]:
        if not isinstance(span, dict):
            return None
        file_id = span.get("file_id")
        mode = span.get("injection_mode")
        start, end = span.get("start"), span.get("end")
        if (
            not isinstance(file_id, str)
            or not isinstance(mode, str)
            or (file_id, mode) not in identities
            or type(start) is not int
            or type(end) is not int
            or start != cursor
            or not start < end <= len(blocks)
        ):
            return None
        block_type = "image_url" if mode == "image" else "text"
        if any(
            not isinstance(block, dict) or block.get("type") != block_type
            for block in blocks[start:end]
        ):
            return None
        spans.append(
            AttachmentSpan(file_id=file_id, injection_mode=mode, start=start, end=end)
        )
        cursor = end
    if cursor != len(blocks):
        return None
    return AttachmentContent(prompt, visible_block, blocks, spans)
