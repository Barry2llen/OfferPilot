from __future__ import annotations

from dataclasses import replace

from langchain_core.messages import HumanMessage

from utils.chat_attachment_content import (
    ATTACHMENT_LAYOUT_KEY,
    ATTACHMENT_LAYOUT_VERSION,
    AttachmentSpan,
    attachment_content,
)

from ..models import CompactedMessage, CompactionAction, CompactionContext


class HistoricalAttachmentCompactor:
    name = "historical_attachments"

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled

    async def apply(self, context: CompactionContext) -> CompactionContext:
        if not self.enabled:
            return context

        # Prefer the newest copy, which is kept in full even if the summary layer runs.
        retained: dict[tuple[str, str], list[list[str | dict]]] = {}
        actions: list[CompactionAction] = []
        rewritten: list[CompactedMessage] = []
        for entry in reversed(context.entries):
            message = entry.rendered
            layout = (
                attachment_content(message)
                if isinstance(message, HumanMessage)
                else None
            )
            if layout is None:
                rewritten.append(entry)
                continue
            blocks: list[str | dict] = [layout.visible_block]
            spans: list[AttachmentSpan] = []
            for span in layout.spans:
                payload = layout.payload(span)
                identity = span["file_id"], span["injection_mode"]
                copies = retained.setdefault(identity, [])
                if payload in copies:
                    continue
                copies.append(payload)
                spans.append(
                    AttachmentSpan(
                        file_id=span["file_id"],
                        injection_mode=span["injection_mode"],
                        start=len(blocks),
                        end=len(blocks) + len(payload),
                    )
                )
                blocks.extend(payload)
            if len(spans) == len(layout.spans):
                rewritten.append(entry)
                continue

            rewritten.append(
                replace(
                    entry,
                    rendered=message.model_copy(
                        update={
                            "content": blocks,
                            "additional_kwargs": {
                                **message.additional_kwargs,
                                ATTACHMENT_LAYOUT_KEY: {
                                    "version": ATTACHMENT_LAYOUT_VERSION,
                                    "spans": spans,
                                },
                            },
                        }
                    ),
                    kind="rewrite",
                    layer=self.name,
                )
            )
            actions.append(
                CompactionAction(
                    layer=self.name,
                    kind="rewrite",
                    sources=entry.sources,
                    reason="Omitted exact attachment blocks already retained in the model view.",
                )
            )
        return context.with_entries(tuple(reversed(rewritten))).add_actions(
            *reversed(actions)
        )
