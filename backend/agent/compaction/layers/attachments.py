from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from langchain_core.messages import HumanMessage

from ..models import CompactedMessage, CompactionAction, CompactionContext


_ATTACHMENT_LAYER = "historical_attachments"


def _valid_attachments(value: object) -> list[dict[str, str]] | None:
    if not isinstance(value, list) or not value:
        return None

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        file_id = item.get("file_id")
        filename = item.get("original_filename") or item.get("filename")
        injection_mode = item.get("injection_mode") or item.get("mode")
        if not all(
            isinstance(field, str) and field.strip()
            for field in (file_id, filename, injection_mode)
        ):
            return None
        normalized.append(
            {
                "file_id": file_id,
                "filename": filename,
                "injection_mode": injection_mode,
            }
        )
    return normalized


def _content_preview(content: object) -> str:
    if isinstance(content, str):
        return content[:800]
    if not isinstance(content, list):
        return ""

    for block in content:
        if isinstance(block, str) and block.strip():
            return block[:800]
        if not isinstance(block, Mapping):
            continue
        block_type = block.get("type")
        text = block.get("text")
        if block_type == "text" and isinstance(text, str) and text.strip():
            return text[:800]
    return ""


def _attachment_reference_view(message: HumanMessage, attachments: list[dict[str, str]]) -> str:
    additional_kwargs = message.additional_kwargs
    display_content = additional_kwargs.get("display_content")
    visible_text = (
        display_content
        if isinstance(display_content, str) and display_content.strip()
        else _content_preview(message.content)
    )
    visible_text = visible_text.strip()[:800]
    if not visible_text:
        visible_text = "（未提供可见用户文本）"

    references = "\n".join(
        f"- {item['file_id']} ({item['filename']}, mode={item['injection_mode']})"
        for item in attachments
    )
    return (
        "[历史附件上下文已压缩]\n\n"
        "用户当时的消息：\n"
        f"{visible_text}\n\n"
        "附件引用：\n"
        f"{references}\n\n"
        "完整附件内容未重复放入本次模型上下文。"
    )


class HistoricalAttachmentCompactor:
    name = _ATTACHMENT_LAYER

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled

    async def apply(self, context: CompactionContext) -> CompactionContext:
        if not self.enabled:
            return context

        actions: list[CompactionAction] = []

        def rewrite(entry: CompactedMessage) -> CompactedMessage:
            message = entry.rendered
            if not isinstance(message, HumanMessage):
                return entry
            attachments = _valid_attachments(message.additional_kwargs.get("attachments"))
            if attachments is None:
                return entry

            rewritten_message = message.model_copy(
                update={"content": _attachment_reference_view(message, attachments)}
            )
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="rewrite",
                    sources=entry.sources,
                    reason="Replaced historical attachment bodies with deterministic file references.",
                )
            )
            return CompactedMessage(
                rendered=rewritten_message,
                sources=entry.sources,
                kind="rewrite",
                layer=self.name,
            )

        units = context.units
        # Protection is evaluated at the unit level so the latest user turn and
        # recent turns cannot be rewritten as historical attachment context.
        protected_entry_sources = {
            source
            for unit in units
            if unit.protected
            for entry in unit.entries
            for source in entry.sources
        }

        def rewrite_if_old(entry: CompactedMessage) -> CompactedMessage:
            if any(source in protected_entry_sources for source in entry.sources):
                return entry
            return rewrite(entry)

        compacted_units = tuple(
            unit
            if unit.protected
            else replace(
                unit,
                entries=tuple(rewrite_if_old(entry) for entry in unit.entries),
            )
            for unit in units
        )
        return context.with_units(compacted_units).add_actions(*actions)


__all__ = ["HistoricalAttachmentCompactor"]
