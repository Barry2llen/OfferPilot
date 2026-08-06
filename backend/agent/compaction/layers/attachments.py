from __future__ import annotations

from collections.abc import Mapping

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
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text[:800]
    return ""


def _attachment_reference_view(
    message: HumanMessage,
    attachments: list[dict[str, str]],
) -> str:
    display_content = message.additional_kwargs.get("display_content")
    visible_text = (
        display_content
        if isinstance(display_content, str) and display_content.strip()
        else _content_preview(message.content)
    )
    visible_text = visible_text.strip()[:800]
    if not visible_text:
        visible_text = "No visible user text was provided."

    references = "\n".join(
        f"- {item['file_id']} ({item['filename']}, mode={item['injection_mode']})"
        for item in attachments
    )
    return (
        "[Historical attachment context compacted]\n\n"
        "User message at that time:\n"
        f"{visible_text}\n\n"
        "Attachment references:\n"
        f"{references}\n\n"
        "Full attachment content is not repeated in this model context."
    )


class HistoricalAttachmentCompactor:
    name = _ATTACHMENT_LAYER

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled

    async def apply(self, context: CompactionContext) -> CompactionContext:
        if not self.enabled:
            return context

        actions: list[CompactionAction] = []
        rewritten_entries: list[CompactedMessage] = []

        for entry in context.entries:
            message = entry.rendered
            attachments = (
                _valid_attachments(message.additional_kwargs.get("attachments"))
                if isinstance(message, HumanMessage)
                else None
            )
            if entry.protected or attachments is None:
                rewritten_entries.append(entry)
                continue

            if isinstance(message.content, str) and message.content.startswith(
                "[Historical attachment context compacted]"
            ):
                rewritten_entries.append(entry)
                continue

            rewritten_entries.append(
                CompactedMessage(
                    rendered=message.model_copy(
                        update={
                            "content": _attachment_reference_view(message, attachments)
                        }
                    ),
                    sources=entry.sources,
                    kind="rewrite",
                    layer=self.name,
                    protected=entry.protected,
                )
            )
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="rewrite",
                    sources=entry.sources,
                    reason=(
                        "Replaced historical attachment bodies with deterministic file references."
                    ),
                )
            )

        return context.with_entries(tuple(rewritten_entries)).add_actions(*actions)


__all__ = ["HistoricalAttachmentCompactor"]
