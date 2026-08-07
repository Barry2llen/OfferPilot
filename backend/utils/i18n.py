"""Request locale negotiation and translations for user-facing API messages."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal

from fastapi import Request

Locale = Literal["zh-CN", "en-US"]
DEFAULT_LOCALE: Locale = "zh-CN"
SUPPORTED_LOCALES: tuple[Locale, Locale] = ("zh-CN", "en-US")


MESSAGES: dict[str, dict[Locale, str]] = {
    "notFound": {
        "zh-CN": "未找到请求的资源。",
        "en-US": "The requested resource was not found.",
    },
    "validation": {
        "zh-CN": "请求参数无效。",
        "en-US": "The request data is invalid.",
    },
    "modelSelectionRequired": {
        "zh-CN": "必须指定模型选择配置。",
        "en-US": "A model selection is required.",
    },
    "modelSelectionNotFound": {
        "zh-CN": "未找到模型选择配置：{id}",
        "en-US": "Model selection not found: {id}",
    },
    "modelProviderNotFound": {
        "zh-CN": "未找到模型供应商：{name}",
        "en-US": "Model provider not found: {name}",
    },
    "modelProviderUnsupported": {
        "zh-CN": "不支持该模型供应商类型。",
        "en-US": "The model provider type is not supported.",
    },
    "modelProviderAlreadyExists": {
        "zh-CN": "模型供应商已存在：{name}",
        "en-US": "Model provider already exists: {name}",
    },
    "modelSelectionAlreadyExists": {
        "zh-CN": "模型选择已存在：{name}",
        "en-US": "Model selection already exists: {name}",
    },
    "providerReferenced": {
        "zh-CN": "模型供应商仍被模型选择引用。",
        "en-US": "The model provider is still referenced by model selections.",
    },
    "chatHistoryNotFound": {
        "zh-CN": "未找到会话历史：{id}",
        "en-US": "Chat history not found: {id}",
    },
    "chatFileNotFound": {
        "zh-CN": "未找到聊天文件：{id}",
        "en-US": "Chat file not found: {id}",
    },
    "resumeNotFound": {
        "zh-CN": "未找到简历：{id}",
        "en-US": "Resume not found: {id}",
    },
    "resumeFileNotFound": {
        "zh-CN": "未找到简历原文件：{id}",
        "en-US": "Resume file not found: {id}",
    },
    "analysisNotFound": {
        "zh-CN": "未找到 JD 分析记录：{id}",
        "en-US": "JD analysis not found: {id}",
    },
    "emptyFile": {
        "zh-CN": "上传的文件为空。",
        "en-US": "The uploaded file is empty.",
    },
    "filenameRequired": {
        "zh-CN": "必须提供上传文件名。",
        "en-US": "An uploaded file name is required.",
    },
    "unsupportedResumeFile": {
        "zh-CN": "不支持的简历文件类型。",
        "en-US": "The resume file type is not supported.",
    },
    "unsupportedChatFile": {
        "zh-CN": "不支持的聊天文件类型。",
        "en-US": "The chat file type is not supported.",
    },
    "unsupportedPreview": {
        "zh-CN": "不支持预览此文件类型。",
        "en-US": "This file type cannot be previewed.",
    },
    "fileProcessing": {
        "zh-CN": "文件处理失败。",
        "en-US": "The file could not be processed.",
    },
    "invalidResume": {
        "zh-CN": "简历内容无效。",
        "en-US": "The resume content is invalid.",
    },
    "invalidJd": {
        "zh-CN": "JD 输入无效。",
        "en-US": "The JD input is invalid.",
    },
    "selectionRequired": {
        "zh-CN": "必须提供 selection_id。",
        "en-US": "selection_id is required.",
    },
    "threadIdRequired": {
        "zh-CN": "使用该命令时必须提供 thread_id。",
        "en-US": "thread_id is required for this command.",
    },
    "choiceRequired": {
        "zh-CN": "使用 query 命令时必须提供 choice。",
        "en-US": "choice is required for a query command.",
    },
    "modelLoadFailed": {
        "zh-CN": "模型加载失败。",
        "en-US": "The model could not be loaded.",
    },
    "modelCallFailed": {
        "zh-CN": "模型调用失败。",
        "en-US": "The model call failed.",
    },
    "contextCompactionFailed": {
        "zh-CN": "上下文压缩失败：{detail}",
        "en-US": "Context compaction failed: {detail}",
    },
    "modelRetry": {
        "zh-CN": "模型调用失败，正在重试（第 {attempt}/{max_attempts} 次）。",
        "en-US": "The model call failed; retrying (attempt {attempt}/{max_attempts}).",
    },
    "agentInterrupted": {
        "zh-CN": "Agent 已中断。",
        "en-US": "The Agent was interrupted.",
    },
    "resumeExtractionFailed": {
        "zh-CN": "简历解析失败。",
        "en-US": "Resume parsing failed.",
    },
    "jdAnalysisFailed": {
        "zh-CN": "JD 分析失败。",
        "en-US": "JD analysis failed.",
    },
    "progressResumeStart": {
        "zh-CN": "开始解析简历。",
        "en-US": "Starting resume parsing.",
    },
    "progressResumeText": {
        "zh-CN": "已提取简历文本。",
        "en-US": "Extracted resume text.",
    },
    "progressResumeTextValidated": {
        "zh-CN": "已验证提取的简历文本。",
        "en-US": "Validated extracted resume text.",
    },
    "progressResumeOcrFallback": {
        "zh-CN": "正在回退到 OCR 文本提取。",
        "en-US": "Falling back to OCR text extraction.",
    },
    "progressResumeOcrText": {
        "zh-CN": "已使用 OCR 提取简历文本。",
        "en-US": "Extracted resume text with OCR.",
    },
    "progressResumePreview": {
        "zh-CN": "已将简历转换为预览图片。",
        "en-US": "Converted the resume to preview images.",
    },
    "progressResumeSections": {
        "zh-CN": "正在提取简历章节。",
        "en-US": "Extracting resume sections.",
    },
    "progressResumeSectionsDone": {
        "zh-CN": "已提取简历章节。",
        "en-US": "Extracted resume sections.",
    },
    "progressResumeFacts": {
        "zh-CN": "正在提取简历章节中的事实。",
        "en-US": "Extracting facts from resume sections.",
    },
    "progressResumeComplete": {
        "zh-CN": "简历解析完成。",
        "en-US": "Completed resume parsing.",
    },
    "progressJdStart": {
        "zh-CN": "正在准备 JD 输入。",
        "en-US": "Preparing JD source inputs.",
    },
    "progressJdPrepared": {
        "zh-CN": "JD 输入已准备完成。",
        "en-US": "Prepared JD source inputs.",
    },
    "progressJdText": {
        "zh-CN": "已从标记工具提取 JD 文本。",
        "en-US": "Extracted JD text from marker tool.",
    },
    "progressJdStructure": {
        "zh-CN": "正在提取 JD 结构。",
        "en-US": "Starting JD structure extraction.",
    },
    "progressJdStructureDone": {
        "zh-CN": "JD 结构提取完成。",
        "en-US": "Extracted JD structure.",
    },
    "progressJdFacts": {
        "zh-CN": "正在提取 JD 需求块中的事实。",
        "en-US": "Extracting facts from JD blocks.",
    },
    "progressJdBlockFacts": {
        "zh-CN": "正在提取 JD 需求块事实。",
        "en-US": "Extracting JD block facts.",
    },
    "progressJdComplete": {
        "zh-CN": "JD 分析完成。",
        "en-US": "Completed JD analysis.",
    },
    "progressJdCompleteNoBlocks": {
        "zh-CN": "JD 分析完成（没有需求块）。",
        "en-US": "Completed JD analysis (no blocks).",
    },
    "progressJdExtractionFailed": {
        "zh-CN": "JD 提取失败。",
        "en-US": "JD extraction failed.",
    },
}


def resolve_locale(value: str | None) -> Locale:
    """Resolve a request header value, falling back to Simplified Chinese."""

    if not value:
        return DEFAULT_LOCALE

    candidates: list[tuple[float, int, str]] = []
    for index, raw_item in enumerate(value.split(",")):
        item = raw_item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split(";")]
        language = parts[0].lower()
        quality = 1.0
        for parameter in parts[1:]:
            name, separator, raw_quality = parameter.partition("=")
            if name.lower() == "q" and separator:
                try:
                    quality = float(raw_quality)
                except ValueError:
                    quality = 0.0
        if quality <= 0:
            continue
        candidates.append((quality, -index, language))

    for _, _, language in sorted(candidates, reverse=True):
        if language == "en-us" or language.startswith("en-") or language == "en":
            return "en-US"
        if language == "zh-cn" or language.startswith("zh-") or language == "zh":
            return "zh-CN"

    return DEFAULT_LOCALE


def request_locale(request: Request) -> Locale:
    locale = getattr(request.state, "locale", None)
    if locale in SUPPORTED_LOCALES:
        return locale
    return resolve_locale(request.headers.get("Accept-Language"))


def translate(key: str, locale: Locale = DEFAULT_LOCALE, **params: Any) -> str:
    """Return a translated message and interpolate only server-owned values."""

    message = MESSAGES.get(key, {}).get(locale) or MESSAGES.get(key, {}).get(DEFAULT_LOCALE)
    if message is None:
        return key
    return message.format(**params)


def localize_model_retry_detail(
    error: Any,
    locale: Locale = DEFAULT_LOCALE,
    *,
    attempt: Any,
    max_attempts: Any,
) -> str:
    """Localize retry status while preserving the provider's technical detail."""

    message = translate(
        "modelRetry",
        locale,
        attempt=attempt or 0,
        max_attempts=max_attempts or 0,
    )
    raw_error = str(error).strip() if error is not None else ""
    return f"{message} {raw_error}" if raw_error else message


def _suffix(raw: str, marker: str) -> str:
    return raw.split(marker, 1)[1].strip()


def localize_error(error: BaseException | str, locale: Locale = DEFAULT_LOCALE) -> str:
    """Translate known application errors without rewriting unknown technical details."""

    raw = str(error)
    name = error.__class__.__name__ if isinstance(error, BaseException) else ""
    lowered = raw.lower()

    if raw in {"Not Found", "404 Not Found"}:
        return translate("notFound", locale)

    for marker, key, parameter in (
        ("Model selection not found:", "modelSelectionNotFound", "id"),
        ("Model provider not found:", "modelProviderNotFound", "name"),
        ("Model provider already exists:", "modelProviderAlreadyExists", "name"),
        ("Model selection already exists:", "modelSelectionAlreadyExists", "name"),
        ("Chat history not found:", "chatHistoryNotFound", "id"),
        ("Chat file not found:", "chatFileNotFound", "id"),
        ("Resume file not found:", "resumeFileNotFound", "id"),
        ("Resume not found:", "resumeNotFound", "id"),
        ("JD analysis not found:", "analysisNotFound", "id"),
        ("Job description analysis not found:", "analysisNotFound", "id"),
    ):
        if raw.startswith(marker):
            return translate(key, locale, **{parameter: _suffix(raw, marker)})

    if "still referenced by model selections" in lowered:
        return translate("providerReferenced", locale)
    if "unsupported provider value" in lowered or name == "UnsupportedModelProviderError":
        return translate("modelProviderUnsupported", locale)
    if "selection_id is required" in lowered:
        return translate("selectionRequired", locale)
    if raw.startswith("Context compaction failed:"):
        marker = "Context compaction failed:"
        return translate(
            "contextCompactionFailed",
            locale,
            detail=_suffix(raw, marker),
        )
    if "uploaded chat file is empty" in lowered or "uploaded file is empty" in lowered:
        return translate("emptyFile", locale)
    if "uploaded file name is required" in lowered:
        return translate("filenameRequired", locale)
    if "legacy .doc files are not supported" in lowered:
        key = "unsupportedChatFile" if "chat" in lowered else "unsupportedResumeFile"
        return translate(key, locale)
    if "unsupported resume file type" in lowered or "unsupported resume" in lowered:
        return translate("unsupportedResumeFile", locale)
    if "unsupported chat file type" in lowered or "unsupported chat" in lowered:
        return translate("unsupportedChatFile", locale)
    if "unsupported injection mode" in lowered or "could not be processed" in lowered:
        return translate("fileProcessing", locale)
    if "preview" in lowered and ("not found" in lowered or "unsupported" in lowered):
        return translate("unsupportedPreview", locale)
    if name == "ChatFileProcessingError":
        return translate("fileProcessing", locale)
    if name in {
        "ResumeParsingError",
        "ResumePreviewDependencyError",
        "ResumePreviewConversionError",
    }:
        return translate("fileProcessing", locale)
    if name == "ChatModelLoadError" or "model selection is required to load" in lowered:
        return translate("modelLoadFailed", locale)
    if name in {"ModelCallExecutionError", "ChatModelLoadError"} or "model call failed" in lowered:
        return translate("modelCallFailed", locale)
    if name in {"ResumeValidationError", "ValidationError", "ModelSelectionValidationError"}:
        return translate("validation", locale)
    if name == "JobDescriptionAnalysisValidationError":
        return translate("invalidJd", locale)
    if name == "NotAResumeError":
        return translate("invalidResume", locale)
    if name.startswith("UnsupportedResumePreview"):
        return translate("unsupportedPreview", locale)
    if name.startswith("UnsupportedResume"):
        return translate("unsupportedResumeFile", locale)
    if name.startswith("UnsupportedChat"):
        return translate("unsupportedChatFile", locale)
    if name.endswith("NotFoundError"):
        return translate("notFound", locale)

    return raw


_PROGRESS_EXACT_KEYS: Mapping[str, str] = {
    "Starting resume extraction.": "progressResumeStart",
    "Extracted resume text.": "progressResumeText",
    "Validated extracted resume text.": "progressResumeTextValidated",
    "Falling back to OCR text extraction.": "progressResumeOcrFallback",
    "Extracted resume text with OCR.": "progressResumeOcrText",
    "Converted resume document to preview images.": "progressResumePreview",
    "Extracting resume sections.": "progressResumeSections",
    "Extracted resume sections.": "progressResumeSectionsDone",
    "Extracting facts from resume sections.": "progressResumeFacts",
    "Updated resume fact extraction progress.": "progressResumeFacts",
    "Completed resume extraction.": "progressResumeComplete",
    "Preparing JD source inputs.": "progressJdStart",
    "Prepared JD source inputs.": "progressJdPrepared",
    "Extracted JD text from marker tool.": "progressJdText",
    "Starting JD structure extraction.": "progressJdStructure",
    "Extracted JD structure.": "progressJdStructureDone",
    "Extracting facts from JD blocks.": "progressJdFacts",
    "Extracting JD block facts.": "progressJdBlockFacts",
    "Completed JD analysis.": "progressJdComplete",
    "Completed JD analysis (no blocks).": "progressJdCompleteNoBlocks",
    "JD extraction failed.": "progressJdExtractionFailed",
    "JD extraction failed: missing marker tool call.": "progressJdExtractionFailed",
    "JD extraction failed: invalid marker tool result.": "progressJdExtractionFailed",
}


def localize_progress_message(message: Any, locale: Locale = DEFAULT_LOCALE) -> Any:
    """Translate known workflow progress messages while preserving model/user text."""

    if not isinstance(message, str):
        return message
    key = _PROGRESS_EXACT_KEYS.get(message)
    if key:
        return translate(key, locale)

    match = re.fullmatch(r"Extracting facts from section: (.*)", message)
    if match:
        if locale == "en-US":
            return message
        return f"正在提取章节「{match.group(1)}」中的事实。"
    match = re.fullmatch(r"Extracted facts from section: (.*)", message)
    if match:
        if locale == "en-US":
            return message
        return f"已提取章节「{match.group(1)}」中的事实。"
    match = re.fullmatch(r"Failed to extract facts from section: (.*)", message)
    if match:
        if locale == "en-US":
            return message
        return f"提取章节「{match.group(1)}」中的事实失败。"

    return message


def localize_validation_message(message: str, locale: Locale) -> str:
    """Keep field locations/types while translating common Pydantic wording."""

    if locale == "en-US":
        return message
    lowered = message.lower()
    if "thread_id is required" in lowered:
        return translate("threadIdRequired", locale)
    if "choice is required" in lowered:
        return translate("choiceRequired", locale)
    if "selection_id is required" in lowered:
        return translate("selectionRequired", locale)
    if "field required" in lowered or "missing" in lowered:
        return "此字段为必填项。"
    if "input should be a valid integer" in lowered:
        return "请输入有效的整数。"
    if "input should be a valid string" in lowered:
        return "请输入有效的文本。"
    if "input should be a valid boolean" in lowered:
        return "请输入有效的布尔值。"
    if "string should have at least" in lowered:
        return "文本长度不足。"
    if "string should have at most" in lowered:
        return "文本长度超出限制。"
    return translate("validation", locale)


__all__ = [
    "DEFAULT_LOCALE",
    "Locale",
    "MESSAGES",
    "SUPPORTED_LOCALES",
    "localize_error",
    "localize_model_retry_detail",
    "localize_progress_message",
    "localize_validation_message",
    "request_locale",
    "resolve_locale",
    "translate",
]
