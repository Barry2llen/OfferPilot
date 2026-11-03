import asyncio
import json
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from pydantic import BaseModel, ValidationError

from agent.interactions import InteractionBroker, InteractionContext, InteractionError
from agent.tools.query import query
from schemas.query import QueryAnswer, QueryRequest
from utils.tool_outputs import summarize_tool_output


def question(mode="multiple", count=4):
    return {
        "type": "query",
        "question": "Choose next steps",
        "selection_mode": mode,
        "options": [
            {"id": str(i), "label": f"Option {i}", "description": f"Use option {i}"}
            for i in range(count)
        ],
    }


@pytest.mark.parametrize("count", [2, 4, 6])
@pytest.mark.parametrize("mode", ["single", "multiple"])
async def test_broker_normalizes_answers_and_keeps_conflicts_atomic(count, mode):
    events: list[tuple[str, dict[str, Any]]] = []

    async def publish(_rid, event, data):
        events.append((event, data))

    broker = InteractionBroker(publish)
    request = question(mode, count)
    task = asyncio.create_task(
        broker.ask(InteractionContext(broker, "r", "t"), request)
    )
    await asyncio.sleep(0)
    try:
        pending = broker.list_pending("r")[0]
        assert {key: pending[key] for key in request} == request
        selected = [str(i) for i in range(count)] if mode == "multiple" else ["0"]
        answer = {"selected_option_ids": selected[::-1], "note": " note "}
        await broker.submit("r", pending["request_id"], answer)
        result = await task
        assert result == {
            "selected_option_ids": selected,
            "free_text": None,
            "note": "note",
        }
        await broker.submit("r", pending["request_id"], result)
        with pytest.raises(InteractionError) as error:
            await broker.submit("r", pending["request_id"], {"free_text": "Different"})
        assert error.value.status_code == 409
        assert [event for event, _ in events] == ["input_required", "input_resolved"]
    finally:
        broker.cancel_run("r")
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "payload",
    [
        {**question(), "options": []},
        {**question(), "options": question()["options"][:1]},
        {**question(), "options": [question()["options"][0]] * 2},
        {**question(), "question": "   "},
        {**question(), "selection_mode": "invalid"},
        {key: value for key, value in question().items() if key != "selection_mode"},
        {**question(), "options": [{"id": "0", "label": " ", "description": "x"}] * 2},
    ],
)
async def test_invalid_questions_never_register_or_publish(payload):
    async def publish(*_args):
        pytest.fail("Invalid questions must not publish an input request")

    broker = InteractionBroker(publish)
    with pytest.raises(ValidationError):
        await broker.ask(InteractionContext(broker, "r", "t"), payload)
    assert not broker.items


@pytest.mark.parametrize(
    "mode,answer",
    [
        ("single", {}),
        ("multiple", {"free_text": "  ", "note": "Just a note"}),
        ("multiple", {"selected_option_ids": ["unknown"]}),
        ("multiple", {"selected_option_ids": ["0", "0"]}),
        ("single", {"selected_option_ids": ["0", "1"]}),
        ("single", {"selected_option_ids": ["0"], "free_text": "custom"}),
        ("multiple", {"selected_option_ids": ["0"], "note": 12}),
        ("multiple", {"selected_option_ids": "0"}),
        ("multiple", {"choice": "firstChoice"}),
    ],
)
async def test_invalid_answers_leave_original_question_waiting(mode, answer):
    async def publish(*_args):
        pass

    broker = InteractionBroker(publish)
    task = asyncio.create_task(
        broker.ask(InteractionContext(broker, "r", "t"), question(mode))
    )
    await asyncio.sleep(0)
    pending = broker.list_pending("r")[0]
    try:
        with pytest.raises(InteractionError) as error:
            await broker.submit("r", pending["request_id"], answer)
        assert error.value.status_code == 422
        assert not task.done()
        assert broker.list_pending("r") == [pending]
        await broker.submit(
            "r", pending["request_id"], {"free_text": " My answer ", "note": " note "}
        )
        assert await task == {
            "selected_option_ids": [],
            "free_text": "My answer",
            "note": "note",
        }
    finally:
        broker.cancel_run("r")
        await asyncio.gather(task, return_exceptions=True)


def test_multiple_answer_combines_all_user_content():
    answer = QueryAnswer(
        selected_option_ids=["3", "1"],
        free_text="  自定义答案  ",
        note=" Additional context ",
    ).for_request(QueryRequest.model_validate(question()))
    assert answer.model_dump() == {
        "selected_option_ids": ["1", "3"],
        "free_text": "自定义答案",
        "note": "Additional context",
    }


def test_tool_schema_exposes_dynamic_options_and_explicit_mode():
    schema_model = query.tool_call_schema
    assert isinstance(schema_model, type) and issubclass(schema_model, BaseModel)
    schema = schema_model.model_json_schema()
    assert set(schema["required"]) == {"question", "selection_mode", "options"}
    assert schema["properties"]["options"]["minItems"] == 2
    assert "maxItems" not in schema["properties"]["options"]
    assert "firstChoice" not in json.dumps(schema)


def test_dynamic_tool_output_summary_retains_complete_display_context():
    artifact = {key: value for key, value in question().items() if key != "type"}
    content = {
        "selected_options": [
            {"id": "0", "label": "Option 0"},
            {"id": "3", "label": "Option 3"},
        ],
        "free_text": "Custom answer",
        "note": "Keep this note",
    }
    output = ToolMessage(
        name="query",
        tool_call_id="call",
        content=json.dumps(content),
        artifact=artifact,
    )
    assert summarize_tool_output("query", output) == {**artifact, **content}
