from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Mapping

from langchain_core.messages import BaseMessage
from langchain_core.runnables.schema import StreamEvent

from agent.workflows.resume_advice import resume_advice
from exceptions import (
    ModelSelectionNotFoundError,
    ModelSelectionValidationError,
    ResumePreviewError,
)
from schemas.config import Config
from schemas.model_selection import ModelSelection
from schemas.resume_advice import ResumeAdviceRequest, ResumeAdviceResponse
from schemas.resume_document import ResumeDocument
from services.model_selection_service import ModelSelectionService
from services.resume_service import ResumeService


@dataclass(slots=True)
class ResumeAdviceGeneration:
    resume_id: int
    model_selection: ModelSelection
    graph: Any


class ResumeAdviceService:
    def __init__(
        self,
        *,
        resume_service: ResumeService,
        model_selection_service: ModelSelectionService,
        config: Config,
    ) -> None:
        self._resume_service = resume_service
        self._model_selection_service = model_selection_service
        self._config = config

    def prepare_generation(
        self,
        *,
        resume_id: int,
        request: ResumeAdviceRequest,
    ) -> ResumeAdviceGeneration:
        resume_detail = self._resume_service.get_resume(resume_id)
        resume = ResumeDocument.model_validate(resume_detail.model_dump())
        model_selection = self._require_model_selection(request.model_selection_id)
        self._require_image_input_model(model_selection)

        # Validate preview generation before starting execution so HTTP endpoints
        # can fail fast with the expected status code.
        resume_images = resume.convert_resume_to_image_base64()
        graph = resume_advice(
            resume=resume,
            resume_images=resume_images,
            model=model_selection,
            config=self._config,
            user_prompt=request.user_prompt,
        )
        return ResumeAdviceGeneration(
            resume_id=resume_id,
            model_selection=model_selection,
            graph=graph,
        )

    async def generate_advice(
        self,
        generation: ResumeAdviceGeneration,
    ) -> ResumeAdviceResponse:
        final_content: str | None = None

        async for event in generation.graph.astream_events({}):
            if event["event"] != "on_chain_end":
                continue

            output = event["data"].get("output")
            final_content = self._extract_output_content(output) or final_content

        if not final_content:
            raise ResumePreviewError("Resume advice response is empty.")

        return ResumeAdviceResponse(
            resume_id=generation.resume_id,
            model_selection_id=generation.model_selection.id or 0,
            content=final_content,
        )

    async def stream_advice(
        self,
        generation: ResumeAdviceGeneration,
    ) -> AsyncIterator[str]:
        final_content: str | None = None

        try:
            async for event in generation.graph.astream_events({}):
                if event["event"] == "on_chat_model_stream":
                    chunk_content = self._extract_stream_chunk_text(event)
                    if chunk_content:
                        yield self._format_sse("token", {"content": chunk_content})
                    continue

                if event["event"] != "on_chain_end":
                    continue

                output = event["data"].get("output")
                final_content = self._extract_output_content(output) or final_content
        except Exception as error:
            yield self._format_sse("error", {"detail": str(error)})
            return

        if not final_content:
            yield self._format_sse(
                "error",
                {"detail": "Resume advice response is empty."},
            )
            return

        yield self._format_sse(
            "done",
            {
                "resume_id": generation.resume_id,
                "model_selection_id": generation.model_selection.id,
                "content": final_content,
            },
        )

    def _require_model_selection(self, model_selection_id: int) -> ModelSelection:
        model_selection = self._model_selection_service.get_by_id(model_selection_id)
        if model_selection is None:
            raise ModelSelectionNotFoundError(
                f"Model selection not found: {model_selection_id}"
            )
        return model_selection

    def _require_image_input_model(self, model_selection: ModelSelection) -> None:
        if model_selection.supports_image_input:
            return
        raise ModelSelectionValidationError(
            "Model selection does not support image input."
        )

    def _extract_output_content(self, output: object) -> str | None:
        if not isinstance(output, Mapping):
            return None

        messages = output.get("messages")
        if not isinstance(messages, list) or not messages:
            return None

        for message in reversed(messages):
            if not isinstance(message, BaseMessage):
                continue
            content = self._coerce_content_to_text(message.content)
            if content:
                return content

        return None

    def _extract_stream_chunk_text(self, event: StreamEvent) -> str:
        chunk = event["data"].get("chunk")
        if chunk is None:
            return ""
        return self._coerce_content_to_text(getattr(chunk, "content", chunk))

    def _coerce_content_to_text(self, content: object) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            return "".join(text_parts)

        return ""

    def _format_sse(self, event: str, data: Mapping[str, Any]) -> str:
        return (
            f"event: {event}\n"
            f"data: {json.dumps(dict(data), ensure_ascii=False)}\n\n"
        )


__all__ = ["ResumeAdviceGeneration", "ResumeAdviceService"]
