from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable
from contextlib import aclosing
from typing import Any, cast

from langchain.tools import BaseTool, ToolRuntime, tool
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field

from agent.interactions import InteractionContext
from schemas.model_selection import ModelSelection
from services.analysis_service import (
    AnalysisBusyError,
    AnalysisHandle,
    AnalysisService,
    AnalysisStartCancelled,
    AnalysisStartError,
)
from utils.custom_events import _adispatch_custom_event_safely
from utils.i18n import Locale, localize_error, resolve_locale

AnalysisToolDependencies = AnalysisService


def _locale(runtime: ToolRuntime[InteractionContext | None]) -> Locale:
    if runtime.context:
        return runtime.context.locale
    return resolve_locale(runtime.config.get("configurable", {}).get("locale"))


def _model_selection(runtime: ToolRuntime[InteractionContext | None]) -> ModelSelection:
    selection = runtime.state.get("model")
    selection = selection() if callable(selection) else selection
    if selection is None or not isinstance(getattr(selection, "id", None), int):
        raise ValueError("A model selection is required for analysis.")
    return cast(ModelSelection, selection)


def _model_dump(value: Any) -> Any:
    return value.model_dump(mode="json") if isinstance(value, BaseModel) else value


def _content_and_artifact(result: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    model_result = {key: value for key, value in result.items() if key != "detail"}
    detail = result.get("detail")
    if detail is not None:
        model_result["result"] = (
            detail.get("result")
            if result.get("resource_type") == "job_description"
            and isinstance(detail, dict)
            else detail
        )
    return json.dumps(model_result, ensure_ascii=False), result


def _error_message(
    runtime: ToolRuntime[InteractionContext | None],
    name: str,
    result: dict[str, Any],
) -> ToolMessage:
    content, artifact = _content_and_artifact(result)
    return ToolMessage(
        content=content,
        artifact=artifact,
        status="error",
        name=name,
        tool_call_id=runtime.tool_call_id or "",
    )


async def _run_analysis(
    start: Awaitable[AnalysisHandle],
    runtime: ToolRuntime[InteractionContext | None],
    name: str,
) -> ToolMessage:
    locale = _locale(runtime)
    handle = None
    try:
        handle = await start
        terminal = None
        async with aclosing(
            handle.manager.events(handle.resource_id, handle.job_id)
        ) as events:
            async for event in events:
                await _adispatch_custom_event_safely(
                    "on_analysis_job_event",
                    {
                        **event.localized(locale),
                        "tool_name": name,
                        "tool_call_id": runtime.tool_call_id,
                        "event": event.event,
                    },
                )
                if event.event in {"final", "error"}:
                    terminal = event
                    break
        if terminal is None:
            raise RuntimeError("Analysis ended without a result.")
        result = {
            **handle.metadata(),
            "status": "parsed" if terminal.event == "final" else "failed",
        }
        if terminal.event == "final":
            result["detail"] = _model_dump(terminal.data.get(handle.manager.record_key))
        else:
            result["error"] = terminal.localized(locale).get("detail", "")
            return _error_message(runtime, name, result)
        content, artifact = _content_and_artifact(result)
        return ToolMessage(
            content=content,
            artifact=artifact,
            status="success",
            name=name,
            tool_call_id=runtime.tool_call_id or "",
        )
    except asyncio.CancelledError as error:
        if isinstance(error, AnalysisStartCancelled):
            handle = error.handle
        if handle:
            cleanup = asyncio.create_task(
                handle.manager.cancel(handle.resource_id, handle.job_id)
            )
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
            terminal = handle.manager.outcome(handle.resource_id, handle.job_id)
            result = {
                **handle.metadata(),
                "status": "failed",
                "error": localize_error("Analysis was cancelled.", locale),
            }
            if terminal and terminal.event == "final":
                result = {
                    **handle.metadata(),
                    "status": "parsed",
                    "detail": _model_dump(terminal.data.get(handle.manager.record_key)),
                }
            elif terminal:
                result["error"] = terminal.localized(locale).get(
                    "detail", result["error"]
                )
            if runtime.context:
                if result["status"] == "parsed":
                    content, artifact = _content_and_artifact(result)
                    runtime.context.messages.append(
                        ToolMessage(
                            content=content,
                            artifact=artifact,
                            status="success",
                            name=name,
                            tool_call_id=runtime.tool_call_id or "",
                        )
                    )
                else:
                    runtime.context.messages.append(
                        _error_message(runtime, name, result)
                    )
        raise
    except AnalysisBusyError as error:
        return _error_message(
            runtime,
            name,
            {
                **error.handle.metadata(),
                "status": "processing",
                "error": localize_error(error, locale),
            },
        )
    except AnalysisStartError as error:
        return _error_message(
            runtime,
            name,
            {
                **error.handle.metadata(),
                "status": "failed",
                "error": localize_error(error, locale),
            },
        )
    except Exception as error:
        if handle:
            await handle.manager.cancel(
                handle.resource_id, handle.job_id, reason=str(error)
            )
        return _error_message(
            runtime,
            name,
            {
                **(handle.metadata() if handle else {}),
                "status": "failed",
                "error": localize_error(error, locale),
            },
        )


def build_resume_analysis_tool(dependencies: AnalysisToolDependencies) -> BaseTool:
    @tool
    async def analyze_resume(
        runtime: ToolRuntime[InteractionContext | None],
        resume_id: int | None = Field(
            default=None,
            description="Existing resume ID to re-analyze. Supply exactly one of resume_id or file_id.",
            examples=[1],
        ),
        file_id: str | None = Field(
            default=None,
            description="File-library ID to copy into a new resume. Supports PDF, DOCX, PNG, JPG and JPEG.",
            examples=["A1B2C3"],
        ),
    ) -> ToolMessage:
        """Analyze an explicitly identified resume and persist its structured result.

        Uses the current chat model. Supply resume_id for an existing resume or
        file_id for a reusable attachment. Waits for completion. A processing
        resume is left running and its existing record is returned with an error.
        Do not infer an analysis request from an attachment alone.
        """
        return await _run_analysis(
            dependencies.start_resume(
                selection=_model_selection(runtime),
                resume_id=resume_id,
                file_id=file_id,
                locale=_locale(runtime),
            ),
            runtime,
            "analyze_resume",
        )

    return analyze_resume


def build_job_description_analysis_tool(
    dependencies: AnalysisToolDependencies,
) -> BaseTool:
    @tool
    async def analyze_job_description(
        runtime: ToolRuntime[InteractionContext | None],
        jd_text: str | None = Field(
            default=None,
            description="JD text explicitly provided by the user. For image attachments use file_ids instead of copying OCR text.",
            examples=["Backend engineer, Python and SQL."],
        ),
        source_url: str | None = Field(
            default=None,
            description="Source URL of the job description.",
            examples=["https://example.com/jobs/123"],
        ),
        file_ids: list[str] = Field(
            default_factory=list,
            description="File-library image IDs (PNG/JPG/JPEG) containing the JD.",
            examples=[["A1B2C3"]],
        ),
    ) -> ToolMessage:
        """Analyze a JD from explicit text, URL and/or image file IDs.

        At least one source is required. Uses the current chat model and always
        creates a new persisted record. Waits for the structured result.
        Do not infer an analysis request from an attachment alone.
        """
        return await _run_analysis(
            dependencies.start_job_description(
                selection=_model_selection(runtime),
                jd_text=jd_text,
                source_url=source_url,
                file_ids=file_ids,
                locale=_locale(runtime),
            ),
            runtime,
            "analyze_job_description",
        )

    return analyze_job_description


def get_analysis_tools(dependencies: AnalysisToolDependencies) -> list[BaseTool]:
    return [
        build_resume_analysis_tool(dependencies),
        build_job_description_analysis_tool(dependencies),
    ]
