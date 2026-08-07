from fastapi.testclient import TestClient

from main import create_app
from utils.i18n import (
    localize_error,
    localize_model_retry_detail,
    localize_progress_message,
    localize_validation_message,
    resolve_locale,
)


def _assert_openapi_documentation_is_english(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"example", "examples"}:
                continue
            if key in {"title", "summary", "description"} and isinstance(item, str):
                assert not any("\u3400" <= character <= "\u9fff" for character in item)
            else:
                _assert_openapi_documentation_is_english(item)
    elif isinstance(value, list):
        for item in value:
            _assert_openapi_documentation_is_english(item)


def test_resolve_locale_uses_supported_languages_and_falls_back_to_chinese() -> None:
    assert resolve_locale(None) == "zh-CN"
    assert resolve_locale("en-US") == "en-US"
    assert resolve_locale("fr-FR, en-GB;q=0.8") == "en-US"
    assert resolve_locale("en-US;q=0, zh-CN;q=0.5") == "zh-CN"
    assert resolve_locale("fr-FR") == "zh-CN"


def test_known_errors_are_localized_without_rewriting_unknown_details() -> None:
    assert (
        localize_error("Model selection not found: 7", "en-US")
        == "Model selection not found: 7"
    )
    assert (
        localize_error("Model selection not found: 7", "zh-CN")
        == "未找到模型选择配置：7"
    )
    technical_detail = "provider returned trace-id=abc123"
    assert localize_error(technical_detail, "en-US") == technical_detail


def test_context_compaction_error_localizes_prefix_and_preserves_detail() -> None:
    raw_error = "Context compaction failed: provider returned trace-id=abc123"

    assert (
        localize_error(raw_error, "zh-CN")
        == "上下文压缩失败：provider returned trace-id=abc123"
    )
    assert localize_error(raw_error, "en-US") == raw_error


def test_known_progress_messages_are_localized_and_unknown_messages_are_preserved() -> None:
    assert (
        localize_progress_message("Starting resume extraction.", "en-US")
        == "Starting resume parsing."
    )
    assert (
        localize_progress_message("Starting resume extraction.", "zh-CN")
        == "开始解析简历。"
    )
    technical_detail = "model-specific progress detail"
    assert localize_progress_message(technical_detail, "zh-CN") == technical_detail


def test_model_retry_detail_localizes_status_and_preserves_provider_error() -> None:
    assert (
        localize_model_retry_detail(
            "401 Unauthorized",
            "en-US",
            attempt=1,
            max_attempts=3,
        )
        == "The model call failed; retrying (attempt 1/3). 401 Unauthorized"
    )
    assert (
        localize_model_retry_detail(
            "401 Unauthorized",
            "zh-CN",
            attempt=1,
            max_attempts=3,
        )
        == "模型调用失败，正在重试（第 1/3 次）。 401 Unauthorized"
    )
    assert (
        localize_model_retry_detail(
            None,
            "en-US",
            attempt=2,
            max_attempts=3,
        )
        == "The model call failed; retrying (attempt 2/3)."
    )


def test_resume_progress_messages_are_localized() -> None:
    messages = (
        (
            "Validated extracted resume text.",
            "已验证提取的简历文本。",
            "Validated extracted resume text.",
        ),
        (
            "Falling back to OCR text extraction.",
            "正在回退到 OCR 文本提取。",
            "Falling back to OCR text extraction.",
        ),
        (
            "Extracted resume text with OCR.",
            "已使用 OCR 提取简历文本。",
            "Extracted resume text with OCR.",
        ),
        (
            "Extracted resume sections.",
            "已提取简历章节。",
            "Extracted resume sections.",
        ),
    )

    for raw_message, zh_message, en_message in messages:
        assert localize_progress_message(raw_message, "zh-CN") == zh_message
        assert localize_progress_message(raw_message, "en-US") == en_message


def test_validation_messages_are_localized() -> None:
    assert (
        localize_validation_message(
            "Value error, thread_id is required when command.type is retry",
            "zh-CN",
        )
        == "使用该命令时必须提供 thread_id。"
    )
    assert (
        localize_validation_message(
            "Value error, thread_id is required when command.type is retry",
            "en-US",
        )
        == "Value error, thread_id is required when command.type is retry"
    )


def test_api_sets_content_language_and_openapi_is_english(
    temporary_app_config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        default_response = client.get("/health")
        english_response = client.get(
            "/health",
            headers={"Accept-Language": "en-US"},
        )
        fallback_response = client.get(
            "/health",
            headers={"Accept-Language": "fr-FR"},
        )
        openapi_response = client.get("/openapi.json")

    assert default_response.headers["content-language"] == "zh-CN"
    assert english_response.headers["content-language"] == "en-US"
    assert fallback_response.headers["content-language"] == "zh-CN"
    assert openapi_response.headers["content-language"] == "zh-CN"
    openapi_payload = openapi_response.json()
    _assert_openapi_documentation_is_english(openapi_payload)
    assert openapi_payload["components"]["schemas"]["ResumeDetail"]["properties"]["summary"]["examples"] == [
        "张三 高级后端开发工程师 Python, FastAPI"
    ]
