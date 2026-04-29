from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from agent.agents.resume_extractor import ResumeExtractorAgent
from exceptions.resume import ResumePreviewConversionError


class FakeStructuredOutputModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[list[Any]] = []

    def invoke(self, messages: list[Any]) -> object:
        self.calls.append(messages)
        return self.response


def test_extract_with_image_wraps_images_in_human_message() -> None:
    model_response = object()
    model = FakeStructuredOutputModel(model_response)
    agent = ResumeExtractorAgent()

    result = agent._extract_with_image_node(
        {
            "structured_output_model": model,
            "resume_images": [
                "data:image/png;base64,page-one",
                "data:image/png;base64,page-two",
            ],
        }
    )

    assert result["resume_profile"] is model_response
    assert len(model.calls) == 1

    messages = model.calls[0]
    assert len(messages) == 2
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)

    content = messages[1].content
    assert isinstance(content, list)
    assert content == [
        {
            "type": "text",
            "text": "Please extract structured information from these resume images.",
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,page-one"},
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,page-two"},
        },
    ]


def test_extract_with_image_raises_when_images_are_empty() -> None:
    agent = ResumeExtractorAgent()

    with pytest.raises(ResumePreviewConversionError, match="No resume images"):
        agent._extract_with_image_node(
            {
                "structured_output_model": FakeStructuredOutputModel(object()),
                "resume_images": [],
            }
        )
