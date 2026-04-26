from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import Command

from agent.tools import get_all_tools
from main import create_app
from schemas.command import BaseCommand
from schemas.config import Config


def _create_model_selection(client: TestClient) -> int:
    provider = client.post(
        "/model-providers",
        json={
            "provider": "OpenAI",
            "name": "default-openai",
        },
    )
    selection = client.post(
        "/model-selections",
        json={
            "provider_name": "default-openai",
            "model_name": "gpt-4o-mini",
        },
    )

    assert provider.status_code == 200
    assert selection.status_code == 200
    return selection.json()["id"]


def _checkpoint(checkpoint_id: str, message: str) -> dict:
    version = f"00000000000000000000000000000001.{uuid4().hex[:16]}"
    return {
        "v": 2,
        "id": checkpoint_id,
        "ts": "2026-04-25T00:00:00+00:00",
        "channel_values": {"messages": [message]},
        "channel_versions": {"messages": version},
        "versions_seen": {"model": {"messages": version}},
        "updated_channels": ["messages"],
        "pending_sends": [],
    }


def _message_checkpoint(checkpoint_id: str, messages: list[object]) -> dict:
    version = f"{checkpoint_id.split('.')[0]}.{uuid4().hex[:16]}"
    return {
        "v": 2,
        "id": checkpoint_id,
        "ts": "2026-04-25T00:00:00+00:00",
        "channel_values": {"messages": messages},
        "channel_versions": {"messages": version},
        "versions_seen": {"model": {"messages": version}},
        "updated_channels": ["messages"],
        "pending_sends": [],
    }


def test_ai_chat_endpoint_invokes_supervisor_and_persists_checkpoint(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        checkpointer = client.app.state.checkpointer
        seen: list[tuple[dict, dict]] = []

        class FakeSupervisorAgent:
            def invoke(self, state: dict, config: dict) -> dict:
                seen.append((state, config))
                checkpoint = _checkpoint(
                    "00000000000000000000000000000001.0000000000000001",
                    "checkpointed",
                )
                checkpointer.put(
                    config,
                    checkpoint,
                    {"source": "input", "step": -1, "run_id": "run-ai", "parents": {}},
                    checkpoint["channel_versions"],
                )
                return {"messages": [AIMessage(content="AI response")]}

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-ai",
            },
        )
        saved = checkpointer.get_tuple({"configurable": {"thread_id": "thread-ai"}})

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread-ai",
        "content": "AI response",
    }
    assert seen[0][0]["model"].id == selection_id
    assert seen[0][0]["messages"][0].content == "hello"
    assert seen[0][1] == {"configurable": {"thread_id": "thread-ai"}}
    assert saved is not None
    assert saved.checkpoint["channel_values"]["messages"] == ["checkpointed"]


def test_ai_chat_endpoint_generates_thread_id_when_missing(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            def invoke(self, state: dict, config: dict) -> dict:
                assert config["configurable"]["thread_id"]
                return {"messages": [AIMessage(content="generated thread")]}

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
            },
        )

    assert response.status_code == 200
    assert response.json()["thread_id"]
    assert response.json()["content"] == "generated thread"


def test_ai_chat_endpoint_returns_structured_multimodal_content(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)
    content_blocks = [
        {
            "type": "text",
            "text": "你好！有什么我可以帮您的吗？",
            "index": 0,
            "extras": {},
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
            "index": 1,
            "extras": {"source": "model"},
        },
    ]

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            def invoke(self, state: dict, config: dict) -> dict:
                return {"messages": [AIMessage(content=content_blocks)]}

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-multimodal",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread-multimodal",
        "content": content_blocks,
    }


def test_ai_chat_histories_endpoint_returns_latest_thread_summaries(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        old_checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="旧会话第一条用户消息"),
                AIMessage(content="旧会话回复"),
            ],
        )
        old_latest_checkpoint = _message_checkpoint(
            "00000000000000000000000000000003.0000000000000001",
            [
                HumanMessage(content="旧会话第一条用户消息"),
                AIMessage(content="旧会话最新回复"),
            ],
        )
        new_checkpoint = _message_checkpoint(
            "00000000000000000000000000000002.0000000000000001",
            [
                HumanMessage(content="新会话第一条用户消息"),
                AIMessage(content="新会话回复"),
            ],
        )

        old_config = checkpointer.put(
            {"configurable": {"thread_id": "thread-old"}},
            old_checkpoint,
            {"source": "input", "step": -1, "run_id": "run-old-1", "parents": {}},
            old_checkpoint["channel_versions"],
        )
        checkpointer.put(
            old_config,
            old_latest_checkpoint,
            {
                "source": "loop",
                "step": 0,
                "run_id": "run-old-2",
                "parents": {"": old_checkpoint["id"]},
            },
            old_latest_checkpoint["channel_versions"],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-new"}},
            new_checkpoint,
            {"source": "input", "step": -1, "run_id": "run-new", "parents": {}},
            new_checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats", params={"limit": 10, "offset": 0})

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 10
    assert payload["offset"] == 0
    assert [item["thread_id"] for item in payload["items"]] == [
        "thread-old",
        "thread-new",
    ]
    assert payload["items"][0]["title"] == "旧会话第一条用户消息"
    assert payload["items"][0]["last_message_preview"] == "旧会话最新回复"
    assert payload["items"][0]["message_count"] == 2
    assert payload["items"][0]["updated_at"]


def test_ai_chat_history_endpoint_returns_normalized_messages(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="请搜索 OfferPilot"),
                AIMessage(content="我会先搜索。"),
                ToolMessage(
                    content="搜索结果",
                    tool_call_id="call-1",
                    name="web_search_exa",
                    status="success",
                ),
                AIMessage(content="OfferPilot 是一个求职辅助服务。"),
            ],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-history", "parents": {}},
            checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats/thread-history/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["thread_id"] == "thread-history"
    assert payload["title"] == "请搜索 OfferPilot"
    assert payload["last_message_preview"] == "OfferPilot 是一个求职辅助服务。"
    assert payload["message_count"] == 4
    assert payload["messages"] == [
        {
            "role": "user",
            "type": "human",
            "content": "请搜索 OfferPilot",
        },
        {
            "role": "assistant",
            "type": "ai",
            "content": "我会先搜索。",
        },
        {
            "role": "tool",
            "type": "tool",
            "content": "搜索结果",
            "name": "web_search_exa",
            "tool_call_id": "call-1",
            "status": "success",
        },
        {
            "role": "assistant",
            "type": "ai",
            "content": "OfferPilot 是一个求职辅助服务。",
        },
    ]


def test_ai_chat_history_endpoint_returns_404_for_missing_thread(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.get("/ai/chats/missing-thread/history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat history not found: missing-thread"


def test_ai_chat_history_delete_endpoint_removes_thread_checkpoints(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="待删除会话"),
                AIMessage(content="待删除回复"),
            ],
        )
        other_checkpoint = _message_checkpoint(
            "00000000000000000000000000000002.0000000000000001",
            [
                HumanMessage(content="保留会话"),
                AIMessage(content="保留回复"),
            ],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-delete"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-delete", "parents": {}},
            checkpoint["channel_versions"],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-keep"}},
            other_checkpoint,
            {"source": "input", "step": -1, "run_id": "run-keep", "parents": {}},
            other_checkpoint["channel_versions"],
        )

        response = client.delete("/ai/chats/thread-delete")
        deleted_history = client.get("/ai/chats/thread-delete/history")
        remaining_history = client.get("/ai/chats/thread-keep/history")
        saved = checkpointer.get_tuple({"configurable": {"thread_id": "thread-delete"}})

    assert response.status_code == 204
    assert response.content == b""
    assert saved is None
    assert deleted_history.status_code == 404
    assert remaining_history.status_code == 200
    assert remaining_history.json()["thread_id"] == "thread-keep"


def test_ai_chat_history_delete_endpoint_returns_404_for_missing_thread(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.delete("/ai/chats/missing-thread")

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat history not found: missing-thread"


def test_ai_chat_endpoint_returns_404_for_missing_selection(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.post(
            "/ai/chat",
            json={
                "selection_id": 999,
                "prompt": "hello",
            },
        )

    assert response.status_code == 404


def test_ai_chat_stream_endpoint_returns_sse_final_event(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                assert version == "v2"
                assert config == {"configurable": {"thread_id": "thread-stream"}}
                assert state["messages"][0].content == "hello"
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessageChunk(content="streamed ")},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessageChunk(content="response")},
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="streamed response")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-stream",
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: thread\ndata: {"thread_id": "thread-stream"}' in response.text
    assert 'event: token\ndata: {"thread_id": "thread-stream", "content": "streamed "}' in response.text
    assert 'event: token\ndata: {"thread_id": "thread-stream", "content": "response"}' in response.text
    assert 'event: final\ndata: {"thread_id": "thread-stream", "content": "streamed response"}' in response.text


def test_ai_chat_stream_endpoint_returns_reasoning_event(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                yield {
                    "event": "on_chat_model_stream",
                    "data": {
                        "chunk": AIMessageChunk(
                            content="",
                            additional_kwargs={"reasoning_content": "正在分析问题。"},
                        )
                    },
                }
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessageChunk(content="最终答案")},
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="最终答案")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-reasoning",
            },
        )

    assert response.status_code == 200
    assert (
        'event: reasoning\ndata: {"thread_id": "thread-reasoning", '
        '"content": "正在分析问题。"}'
        in response.text
    )
    assert (
        'event: token\ndata: {"thread_id": "thread-reasoning", '
        '"content": "最终答案"}'
        in response.text
    )
    assert (
        'event: final\ndata: {"thread_id": "thread-reasoning", '
        '"content": "最终答案"}'
        in response.text
    )


def test_ai_chat_stream_endpoint_returns_structured_final_content(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)
    content_blocks = [
        {
            "type": "text",
            "text": "你好！有什么我可以帮您的吗？",
            "index": 0,
            "extras": {},
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="},
            "index": 1,
            "extras": {},
        },
    ]

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessageChunk(content=content_blocks)},
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content=content_blocks)]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-stream-multimodal",
            },
        )

    assert response.status_code == 200
    assert (
        'event: token\ndata: {"thread_id": "thread-stream-multimodal", '
        '"content": "你好！有什么我可以帮您的吗？"}'
        in response.text
    )
    assert (
        'event: final\ndata: {"thread_id": "thread-stream-multimodal", '
        '"content": [{"type": "text", "text": "你好！有什么我可以帮您的吗？", '
        '"index": 0, "extras": {}}, {"type": "image_url", "image_url": '
        '{"url": "data:image/png;base64,iVBORw0KGgo="}, "index": 1, "extras": {}}]}'
        in response.text
    )


def test_ai_chat_stream_endpoint_returns_tool_events(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                yield {
                    "event": "on_tool_start",
                    "name": "web_search_exa",
                    "data": {"input": {"query": "OfferPilot"}},
                }
                yield {
                    "event": "on_tool_end",
                    "name": "web_search_exa",
                    "data": {"output": "search result"},
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-tools",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_start\ndata: {"thread_id": "thread-tools", "tool_name": "web_search_exa", "input": {"query": "OfferPilot"}}'
        in response.text
    )
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-tools", "tool_name": "web_search_exa", "output": "search result"}'
        in response.text
    )
    assert 'event: final\ndata: {"thread_id": "thread-tools", "content": "done"}' in response.text


def test_ai_chat_stream_endpoint_returns_tool_error_event(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                yield {
                    "event": "on_tool_end",
                    "name": "web_search_exa",
                    "data": {
                        "output": ToolMessage(
                            content="tool failed",
                            tool_call_id="call-1",
                            name="web_search_exa",
                            status="error",
                        )
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="fallback")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-tool-error",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_error\ndata: {"thread_id": "thread-tool-error", "tool_name": "web_search_exa", "detail": "tool failed"}'
        in response.text
    )
    assert 'event: final\ndata: {"thread_id": "thread-tool-error", "content": "fallback"}' in response.text


def test_ai_chat_stream_endpoint_returns_interrupt_event_without_final(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    class FakeInterrupt:
        def __init__(self) -> None:
            self.value = {
                "type": "error",
                "message": "Model call failed after 2 retries.",
            }
            self.id = "interrupt-1"

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                yield {
                    "event": "on_chain_stream",
                    "data": {"chunk": {"__interrupt__": (FakeInterrupt(),)}},
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="should not emit")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-interrupt",
            },
        )

    assert response.status_code == 200
    assert (
        'event: interrupt\ndata: {"thread_id": "thread-interrupt", "type": "error", "message": "Model call failed after 2 retries.", "id": "interrupt-1"}'
        in response.text
    )
    assert "event: final" not in response.text


def test_ai_chat_stream_endpoint_resumes_retry_command(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)
    seen: list[tuple[object, dict, str]] = []

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: object,
                config: dict,
                *,
                version: str,
            ):
                seen.append((state, config, version))
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="retried response")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "thread_id": "thread-retry",
                "command": {"type": "retry"},
            },
        )

    assert response.status_code == 200
    agent_input, config, version = seen[0]
    assert isinstance(agent_input, Command)
    assert agent_input.resume == {"type": "retry"}
    assert config == {"configurable": {"thread_id": "thread-retry"}}
    assert version == "v2"
    assert 'event: final\ndata: {"thread_id": "thread-retry", "content": "retried response"}' in response.text


def test_ai_chat_stream_endpoint_rejects_retry_without_thread_id(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "command": {"type": "retry"},
            },
        )

    assert response.status_code == 422
    assert "thread_id is required" in response.text


def test_ai_chat_stream_openapi_documents_interrupt_and_retry(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        payload = client.get("/openapi.json").json()

    stream_operation = payload["paths"]["/ai/chat/stream"]["post"]
    assert "interrupt" in stream_operation["responses"]["200"]["description"]
    assert "reasoning" in stream_operation["responses"]["200"]["description"]
    assert "retry" in stream_operation["description"]


def test_ai_chat_history_openapi_documents_history_endpoints(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        payload = client.get("/openapi.json").json()

    assert "/ai/chats" in payload["paths"]
    assert "/ai/chats/{thread_id}/history" in payload["paths"]
    assert "delete" in payload["paths"]["/ai/chats/{thread_id}"]
    assert payload["paths"]["/ai/chats"]["get"]["summary"] == "查询 AI 会话历史列表"
    assert payload["paths"]["/ai/chats/{thread_id}"]["delete"]["summary"] == "删除 AI 会话历史"
    assert (
        payload["paths"]["/ai/chats/{thread_id}/history"]["get"]["summary"]
        == "查询 AI 会话历史详情"
    )


def test_base_command_accepts_retry_without_prompt() -> None:
    command: BaseCommand = {"type": "retry"}

    assert command["type"] == "retry"
    assert "prompt" not in command


def test_get_all_tools_builds_exa_tools_from_config() -> None:
    config = Config(exa_api_key="test-exa-key")

    tools = get_all_tools(config)

    assert [tool.name for tool in tools] == [
        "web_search_exa",
        "web_fetch_exa",
        "find_similar_exa",
    ]
