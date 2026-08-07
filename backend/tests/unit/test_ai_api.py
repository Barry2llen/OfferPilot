import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from agent.tools import get_all_tools
from db.models import ChatFileORM, ChatThreadFileORM
from main import create_app
from schemas.command import BaseCommand
from schemas.config import Config


def _create_model_selection(
    client: TestClient,
    *,
    provider_name: str = "default-openai",
    model_name: str = "gpt-4o-mini",
    supports_image_input: bool = False,
) -> int:
    provider = client.post(
        "/model-providers",
        json={
            "provider": "OpenAI",
            "name": provider_name,
        },
    )
    selection = client.post(
        "/model-selections",
        json={
            "provider_name": provider_name,
            "model_name": model_name,
            "supports_image_input": supports_image_input,
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
            async def ainvoke(self, state: dict, config: dict) -> dict:
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
    assert seen[0][1] == {
        "configurable": {"thread_id": "thread-ai"},
        "recursion_limit": 100,
    }
    assert saved is not None
    assert saved.checkpoint["channel_values"]["messages"] == ["checkpointed"]


def test_ai_chat_endpoint_returns_localized_502_for_interrupt(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    class FakeInterrupt:
        value = {
            "type": "error",
            "message": "Context compaction failed: provider returned trace-id=abc123",
        }
        id = "interrupt-context-compaction"

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def ainvoke(self, state: dict, config: dict) -> dict:
                del state, config
                return {
                    "messages": [],
                    "__interrupt__": (FakeInterrupt(),),
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        chinese = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-context-compaction-zh",
            },
            headers={"Accept-Language": "zh-CN"},
        )
        english = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-context-compaction-en",
            },
            headers={"Accept-Language": "en-US"},
        )

    assert chinese.status_code == 502
    assert chinese.headers["content-language"] == "zh-CN"
    assert chinese.json() == {
        "detail": "上下文压缩失败：provider returned trace-id=abc123"
    }
    assert english.status_code == 502
    assert english.headers["content-language"] == "en-US"
    assert english.json() == {
        "detail": "Context compaction failed: provider returned trace-id=abc123"
    }


def test_ai_chat_endpoint_generates_thread_id_when_missing(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def ainvoke(self, state: dict, config: dict) -> dict:
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


def test_ai_chat_endpoint_uses_configured_graph_recursion_limit(
    temporary_app_config: Config,
) -> None:
    config = temporary_app_config.model_copy(update={"graph_recursion_limit": 250})
    app = create_app(config)
    seen_configs: list[dict] = []

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def ainvoke(self, state: dict, config: dict) -> dict:
                seen_configs.append(config)
                return {"messages": [AIMessage(content="configured limit")]}

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-recursion-limit",
            },
        )

    assert response.status_code == 200
    assert seen_configs == [
        {
            "configurable": {"thread_id": "thread-recursion-limit"},
            "recursion_limit": 250,
        }
    ]


def test_ai_chat_endpoint_falls_back_to_reasoning_content_when_content_is_empty(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        class FakeSupervisorAgent:
            async def ainvoke(self, state: dict, config: dict) -> dict:
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            additional_kwargs={
                                "reasoning_content": "你好！今天有什么可以帮你的吗？"
                            },
                        )
                    ]
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat",
            json={
                "selection_id": selection_id,
                "prompt": "你好",
                "thread_id": "thread-reasoning-fallback",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "thread_id": "thread-reasoning-fallback",
        "content": "你好！今天有什么可以帮你的吗？",
    }


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
            async def ainvoke(self, state: dict, config: dict) -> dict:
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
                    name="custom_tool",
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
            "name": "custom_tool",
            "tool_call_id": "call-1",
            "status": "success",
        },
        {
            "role": "assistant",
            "type": "ai",
            "content": "OfferPilot 是一个求职辅助服务。",
        },
    ]


def test_ai_chat_history_hides_compaction_sidecar_and_reports_success_marker(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="原始用户消息"),
                AIMessage(content="原始助手消息"),
            ],
        )
        checkpoint["channel_values"]["context_compaction"] = {
            "messages": [
                SystemMessage(content="[Historical context summary]\n隐藏摘要"),
                HumanMessage(content="紧凑视图中的最近消息"),
            ],
            "source_message_count": 2,
            "source_message_ids": [None, None],
            "status": "complete",
            "auto_compacted": True,
        }
        context_version = f"context.{uuid4().hex[:16]}"
        checkpoint["channel_versions"]["context_compaction"] = context_version
        checkpoint["updated_channels"].append("context_compaction")
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history-compacted"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-history-compacted", "parents": {}},
            checkpoint["channel_versions"],
        )

        list_response = client.get("/ai/chats", params={"limit": 10, "offset": 0})
        detail_response = client.get("/ai/chats/thread-history-compacted/history")

    assert list_response.status_code == 200
    compacted_item = next(
        item
        for item in list_response.json()["items"]
        if item["thread_id"] == "thread-history-compacted"
    )
    assert compacted_item["context_compacted"] is True
    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["context_compacted"] is True
    assert [message["content"] for message in payload["messages"]] == [
        "原始用户消息",
        "原始助手消息",
    ]
    assert "隐藏摘要" not in detail_response.text


def test_ai_chat_history_returns_reasoning_content_when_assistant_content_is_empty(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="你好"),
                AIMessage(
                    content="",
                    additional_kwargs={
                        "reasoning_content": "你好！今天有什么可以帮你的吗？"
                    },
                ),
            ],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history-reasoning"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-history-reasoning", "parents": {}},
            checkpoint["channel_versions"],
        )

        list_response = client.get("/ai/chats", params={"limit": 10, "offset": 0})
        detail_response = client.get("/ai/chats/thread-history-reasoning/history")

    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["items"][0]["thread_id"] == "thread-history-reasoning"
    assert list_payload["items"][0]["last_message_preview"] == "你好！今天有什么可以帮你的吗？"

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["last_message_preview"] == "你好！今天有什么可以帮你的吗？"
    assert detail_payload["messages"][-1] == {
        "role": "assistant",
        "type": "ai",
        "content": "",
        "reasoning": "你好！今天有什么可以帮你的吗？",
    }


def test_ai_chat_history_keeps_assistant_content_and_reasoning_separate(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="搜索 DeepSeek"),
                AIMessage(
                    content="好的，我先搜索。",
                    additional_kwargs={
                        "reasoning_content": "需要先查询最新信息。",
                        "reasoning_duration_ms": 12000,
                    },
                ),
                ToolMessage(
                    content="搜索结果",
                    tool_call_id="call-search",
                    name="custom_tool",
                    status="success",
                ),
            ],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history-split-reasoning"}},
            checkpoint,
            {
                "source": "input",
                "step": -1,
                "run_id": "run-history-split-reasoning",
                "parents": {},
            },
            checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats/thread-history-split-reasoning/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["messages"][1] == {
        "role": "assistant",
        "type": "ai",
        "content": "好的，我先搜索。",
        "reasoning": "需要先查询最新信息。",
        "reasoning_duration_ms": 12000,
    }


def test_ai_chat_history_summarizes_web_search_tool_messages(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="搜索 DeepSeek"),
                ToolMessage(
                    content=[
                        {
                            "type": "text",
                            "text": (
                                "Title: DeepSeek News\n"
                                "URL: https://example.com/deepseek\n"
                                "Favicon: https://example.com/favicon.ico\n"
                                "Text: private page text"
                            ),
                        }
                    ],
                    tool_call_id="call-search",
                    name="web_search",
                    status="success",
                ),
                AIMessage(content="搜索完成。"),
            ],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history-search"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-history-search", "parents": {}},
            checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats/thread-history-search/history")

    assert response.status_code == 200
    tool_message = response.json()["messages"][1]
    assert tool_message == {
        "role": "tool",
        "type": "tool",
        "content": [
            {
                "url": "https://example.com/deepseek",
                "title": "DeepSeek News",
                "favicon": "https://example.com/favicon.ico",
            }
        ],
        "name": "web_search",
        "tool_call_id": "call-search",
        "status": "success",
    }
    assert "private page text" not in response.text


def test_ai_chat_history_summarizes_query_tool_message(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="需要我选择下一步"),
                ToolMessage(
                    content=json.dumps(
                        {
                            "choice": "firstChoice",
                            "note": "按推荐方案继续。",
                        },
                        ensure_ascii=False,
                    ),
                    artifact={
                        "question": "下一步要怎么处理？",
                        "firstChoice": "使用推荐方案",
                        "firstChoiceDescription": "按系统推荐的完整方案继续推进。",
                        "secondChoice": "只做后端",
                        "secondChoiceDescription": "只处理后端协议和测试。",
                        "thirdChoice": "暂不处理",
                        "thirdChoiceDescription": "先暂停这次调整。",
                        "internal": "should be hidden",
                    },
                    tool_call_id="call-query",
                    name="query",
                    status="success",
                ),
                AIMessage(content="继续处理。"),
            ],
        )
        raw_tool_message = checkpoint["channel_values"]["messages"][1]
        assert raw_tool_message.content == json.dumps(
            {
                "choice": "firstChoice",
                "note": "按推荐方案继续。",
            },
            ensure_ascii=False,
        )
        assert "question" not in raw_tool_message.content
        assert "firstChoiceDescription" not in raw_tool_message.content
        assert "使用推荐方案" not in raw_tool_message.content
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history-query"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-history-query", "parents": {}},
            checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats/thread-history-query/history")

    assert response.status_code == 200
    tool_message = response.json()["messages"][1]
    assert tool_message == {
        "role": "tool",
        "type": "tool",
        "content": {
            "question": "下一步要怎么处理？",
            "choice": "firstChoice",
            "note": "按推荐方案继续。",
            "firstChoice": "使用推荐方案",
            "firstChoiceDescription": "按系统推荐的完整方案继续推进。",
            "secondChoice": "只做后端",
            "secondChoiceDescription": "只处理后端协议和测试。",
            "thirdChoice": "暂不处理",
            "thirdChoiceDescription": "先暂停这次调整。",
        },
        "name": "query",
        "tool_call_id": "call-query",
        "status": "success",
    }
    assert "should be hidden" not in response.text


def test_ai_chat_history_summarizes_web_fetch_tool_messages(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        checkpointer = client.app.state.checkpointer
        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(content="读取 DeepSeek 文档"),
                ToolMessage(
                    content=(
                        "[Result(url='https://api-docs.deepseek.com/zh-cn/', "
                        "title='DeepSeek API Docs', "
                        "favicon='https://api-docs.deepseek.com/favicon.ico', "
                        "text='private page text')]"
                    ),
                    tool_call_id="call-fetch",
                    name="web_fetch_exa",
                    status="success",
                ),
                AIMessage(content="读取完成。"),
            ],
        )
        checkpointer.put(
            {"configurable": {"thread_id": "thread-history-fetch"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-history-fetch", "parents": {}},
            checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats/thread-history-fetch/history")

    assert response.status_code == 200
    tool_message = response.json()["messages"][1]
    assert tool_message == {
        "role": "tool",
        "type": "tool",
        "content": [
            {
                "url": "https://api-docs.deepseek.com/zh-cn/",
                "title": "DeepSeek API Docs",
                "favicon": "https://api-docs.deepseek.com/favicon.ico",
            }
        ],
        "name": "web_fetch_exa",
        "tool_call_id": "call-fetch",
        "status": "success",
    }
    assert "private page text" not in response.text


def test_ai_chat_history_endpoint_returns_404_for_missing_thread(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        response = client.get(
            "/ai/chats/missing-thread/history",
            headers={"Accept-Language": "en-US"},
        )

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
        response = client.delete(
            "/ai/chats/missing-thread",
            headers={"Accept-Language": "en-US"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Chat history not found: missing-thread"


def test_ai_chat_stream_endpoint_accepts_multipart_text_file_and_lists_chat_files(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(temporary_app_config)
    seen_states: list[dict] = []

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        file_path = workspace_tmp_dir / "notes.md"
        file_path.write_text("alpha\nbeta", encoding="utf-8")

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                seen_states.append(state)
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        with file_path.open("rb") as uploaded:
            response = client.post(
                "/ai/chat/stream",
                data={
                    "selection_id": str(selection_id),
                    "prompt": "请总结附件",
                    "thread_id": "thread-text-file",
                },
                files={"files": ("notes.md", uploaded, "text/markdown")},
            )

        files_response = client.get("/ai/files")

    assert response.status_code == 200
    assert files_response.status_code == 200
    listed_files = files_response.json()
    assert len(listed_files) == 1
    assert listed_files[0]["original_filename"] == "notes.md"
    assert listed_files[0]["reference_count"] == 1
    assert '"requires_image_input": false' in response.text
    assert '"original_filename": "notes.md"' in response.text
    assert '"injection_mode": "text"' in response.text

    human_message = seen_states[0]["messages"][0]
    assert human_message.additional_kwargs["display_content"] == "请总结附件"
    assert human_message.additional_kwargs["attachments"][0]["original_filename"] == "notes.md"
    assert isinstance(human_message.content, list)
    assert "notes.md" in human_message.content[0]["text"]
    assert "alpha" in human_message.content[1]["text"]


def test_ai_chat_stream_endpoint_accepts_attachment_without_prompt(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(temporary_app_config)
    seen_states: list[dict] = []

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)
        file_path = workspace_tmp_dir / "attachment-only.md"
        file_path.write_text("alpha\nbeta", encoding="utf-8")

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                seen_states.append(state)
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        with file_path.open("rb") as uploaded:
            response = client.post(
                "/ai/chat/stream",
                data={
                    "selection_id": str(selection_id),
                    "thread_id": "thread-attachment-only",
                },
                files={"files": ("attachment-only.md", uploaded, "text/markdown")},
            )

    assert response.status_code == 200
    assert '"original_filename": "attachment-only.md"' in response.text

    human_message = seen_states[0]["messages"][0]
    assert human_message.additional_kwargs["display_content"] == ""
    assert isinstance(human_message.content, list)
    assert "请分析这些附件内容。" in human_message.content[0]["text"]
    assert "attachment-only.md" in human_message.content[0]["text"]
    assert "alpha" in human_message.content[1]["text"]


def test_ai_chat_stream_endpoint_sends_image_attachment_as_image_url_block(
    temporary_app_config: Config,
    workspace_tmp_dir: Path,
) -> None:
    app = create_app(temporary_app_config)
    seen_states: list[dict] = []

    with TestClient(app) as client:
        selection_id = _create_model_selection(
            client,
            provider_name="vision-openai",
            model_name="gpt-4o-vision",
            supports_image_input=True,
        )
        file_path = workspace_tmp_dir / "flash.png"
        file_path.write_bytes(b"fake-png")

        class FakeSupervisorAgent:
            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                seen_states.append(state)
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        with file_path.open("rb") as uploaded:
            response = client.post(
                "/ai/chat/stream",
                data={
                    "selection_id": str(selection_id),
                    "prompt": "解析图片",
                    "thread_id": "thread-image-file",
                },
                files={"files": ("flash.png", uploaded, "image/png")},
            )

    assert response.status_code == 200
    assert '"requires_image_input": true' in response.text
    assert '"original_filename": "flash.png"' in response.text
    assert '"injection_mode": "image"' in response.text

    human_message = seen_states[0]["messages"][0]
    assert human_message.additional_kwargs["display_content"] == "解析图片"
    assert human_message.additional_kwargs["attachments"][0]["original_filename"] == "flash.png"
    assert isinstance(human_message.content, list)
    assert human_message.content[0]["type"] == "text"
    assert "flash.png" in human_message.content[0]["text"]
    assert human_message.content[1] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,ZmFrZS1wbmc="},
    }


def test_ai_chat_history_prefers_display_content_and_returns_attachments(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        session = client.app.state.database.get_session_factory()()
        try:
            session.add(
                ChatFileORM(
                    id="A1B2C3",
                    storage_path="data/chat_files/a1b2c3.md",
                    original_filename="notes.md",
                    media_type="text/markdown",
                    size_bytes=12,
                )
            )
            session.add(
                ChatThreadFileORM(
                    thread_id="thread-display-content",
                    file_id="A1B2C3",
                    injection_mode="text",
                )
            )
            session.commit()
        finally:
            session.close()

        checkpoint = _message_checkpoint(
            "00000000000000000000000000000001.0000000000000001",
            [
                HumanMessage(
                    content=[
                        {"type": "text", "text": "用户不可见的隐藏附件正文"},
                    ],
                    additional_kwargs={
                        "display_content": "用户可见提问",
                        "attachments": [
                            {
                                "file_id": "A1B2C3",
                                "original_filename": "notes.md",
                                "media_type": "text/markdown",
                                "injection_mode": "text",
                            }
                        ],
                    },
                ),
                AIMessage(content="处理完成。"),
            ],
        )
        client.app.state.checkpointer.put(
            {"configurable": {"thread_id": "thread-display-content"}},
            checkpoint,
            {"source": "input", "step": -1, "run_id": "run-display-content", "parents": {}},
            checkpoint["channel_versions"],
        )

        response = client.get("/ai/chats/thread-display-content/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["attachment_count"] == 1
    assert payload["requires_image_input"] is False
    assert payload["messages"][0] == {
        "role": "user",
        "type": "human",
        "content": "用户可见提问",
        "attachments": [
            {
                "file_id": "A1B2C3",
                "original_filename": "notes.md",
                "media_type": "text/markdown",
                "injection_mode": "text",
            }
        ],
    }
    assert "隐藏附件正文" not in response.text


def test_ai_chat_history_delete_endpoint_keeps_reused_files_until_last_thread_deleted(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        upload_dir = Path(temporary_app_config.chat_file_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = upload_dir / "shared.txt"
        stored_path.write_text("shared content", encoding="utf-8")

        session = client.app.state.database.get_session_factory()()
        try:
            session.add(
                ChatFileORM(
                    id="SHARED",
                    storage_path=str(stored_path),
                    original_filename="shared.txt",
                    media_type="text/plain",
                    size_bytes=len("shared content"),
                )
            )
            session.add_all(
                [
                    ChatThreadFileORM(
                        thread_id="thread-file-a",
                        file_id="SHARED",
                        injection_mode="text",
                    ),
                    ChatThreadFileORM(
                        thread_id="thread-file-b",
                        file_id="SHARED",
                        injection_mode="text",
                    ),
                ]
            )
            session.commit()
        finally:
            session.close()

        for thread_id in ("thread-file-a", "thread-file-b"):
            checkpoint = _message_checkpoint(
                f"{uuid4().hex}.0000000000000001",
                [HumanMessage(content=f"会话 {thread_id}")],
            )
            client.app.state.checkpointer.put(
                {"configurable": {"thread_id": thread_id}},
                checkpoint,
                {"source": "input", "step": -1, "run_id": f"run-{thread_id}", "parents": {}},
                checkpoint["channel_versions"],
            )

        first_delete = client.delete("/ai/chats/thread-file-a")
        files_after_first_delete = client.get("/ai/files")
        second_delete = client.delete("/ai/chats/thread-file-b")
        files_after_second_delete = client.get("/ai/files")

    assert first_delete.status_code == 204
    assert second_delete.status_code == 204
    assert files_after_first_delete.status_code == 200
    assert len(files_after_first_delete.json()) == 1
    assert files_after_second_delete.status_code == 200
    assert files_after_second_delete.json() == []
    assert stored_path.exists() is False


def test_ai_chat_endpoints_allow_non_vision_model_when_thread_requires_image_input(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        vision_selection_id = _create_model_selection(
            client,
            provider_name="vision-openai",
            model_name="gpt-4o-vision",
            supports_image_input=True,
        )
        text_selection_id = _create_model_selection(
            client,
            provider_name="text-openai",
            model_name="gpt-4o-text",
            supports_image_input=False,
        )

        image_path = Path(temporary_app_config.chat_file_upload_dir)
        image_path.mkdir(parents=True, exist_ok=True)
        (image_path / "vision.png").write_bytes(b"fake-png")

        session = client.app.state.database.get_session_factory()()
        try:
            session.add(
                ChatFileORM(
                    id="IMG001",
                    storage_path=str(image_path / "vision.png"),
                    original_filename="vision.png",
                    media_type="image/png",
                    size_bytes=8,
                )
            )
            session.add(
                ChatThreadFileORM(
                    thread_id="thread-requires-vision",
                    file_id="IMG001",
                    injection_mode="image",
                )
            )
            session.commit()
        finally:
            session.close()

        class FakeSupervisorAgent:
            async def ainvoke(self, state: dict, config: dict) -> dict:
                return {"messages": [AIMessage(content="text ok")]}

            async def astream_events(
                self,
                state: dict,
                config: dict,
                *,
                version: str,
            ):
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="vision ok")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": text_selection_id,
                "prompt": "继续分析",
                "thread_id": "thread-requires-vision",
            },
        )

        basic_response = client.post(
            "/ai/chat",
            json={
                "selection_id": text_selection_id,
                "prompt": "继续分析",
                "thread_id": "thread-requires-vision",
            },
        )

        allowed_response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": vision_selection_id,
                "prompt": "继续分析",
                "thread_id": "thread-requires-vision",
            },
        )

    assert response.status_code == 200
    assert '"requires_image_input": true' in response.text
    assert basic_response.status_code == 200
    assert basic_response.json()["content"] == "text ok"
    assert allowed_response.status_code == 200


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
                assert config == {
                    "configurable": {"thread_id": "thread-stream"},
                    "recursion_limit": 100,
                }
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
    assert (
        'event: thread\ndata: {"thread_id": "thread-stream", '
        '"resolved_attachments": [], "attachment_count": 0, '
        '"requires_image_input": false}'
        in response.text
    )
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
                    "event": "on_custom_event",
                    "name": "on_reasoning_done",
                    "data": {"duration_ms": 12000},
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
        'event: reasoning_done\ndata: {"thread_id": "thread-reasoning", '
        '"duration_ms": 12000}'
        in response.text
    )
    assert (
        'event: final\ndata: {"thread_id": "thread-reasoning", '
        '"content": "最终答案"}'
        in response.text
    )


def test_ai_chat_stream_endpoint_returns_context_compaction_lifecycle_events(
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
                del state, config, version
                for phase in ("started", "completed", "failed"):
                    yield {
                        "event": "on_custom_event",
                        "name": "on_context_compaction",
                        "data": {"phase": phase},
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
                "thread_id": "thread-context-compaction-events",
            },
        )

    assert response.status_code == 200
    for phase in ("started", "completed", "failed"):
        assert (
            f'event: context_compaction\ndata: {{"thread_id": "thread-context-compaction-events", "phase": "{phase}"}}'
            in response.text
        )


def test_ai_chat_stream_endpoint_falls_back_to_reasoning_content_when_final_content_is_empty(
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
                            additional_kwargs={
                                "reasoning_content": "你好！今天有什么可以帮你的吗？"
                            },
                        )
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {
                        "output": {
                            "messages": [
                                AIMessage(
                                    content="",
                                    additional_kwargs={
                                        "reasoning_content": "你好！今天有什么可以帮你的吗？"
                                    },
                                )
                            ]
                        }
                    },
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "你好",
                "thread_id": "thread-stream-reasoning-fallback",
            },
        )

    assert response.status_code == 200
    assert (
        'event: reasoning\ndata: {"thread_id": "thread-stream-reasoning-fallback", '
        '"content": "你好！今天有什么可以帮你的吗？"}'
        in response.text
    )
    assert (
        'event: final\ndata: {"thread_id": "thread-stream-reasoning-fallback", '
        '"content": "你好！今天有什么可以帮你的吗？"}'
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
                    "name": "custom_tool",
                    "data": {"input": {"query": "OfferPilot"}},
                }
                yield {
                    "event": "on_tool_end",
                    "name": "custom_tool",
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
        'event: tool_start\ndata: {"thread_id": "thread-tools", "tool_name": "custom_tool", "input": {"query": "OfferPilot"}}'
        in response.text
    )
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-tools", "tool_name": "custom_tool", "output": "search result"}'
        in response.text
    )
    assert 'event: final\ndata: {"thread_id": "thread-tools", "content": "done"}' in response.text


def test_ai_chat_stream_endpoint_summarizes_web_search_tool_output(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    class FakeSearchResult:
        def __init__(
            self,
            *,
            url: str,
            title: str | None = None,
            favicon: str | None = None,
            highlights: list[str] | None = None,
        ) -> None:
            self.url = url
            self.title = title
            self.favicon = favicon
            self.highlights = highlights

    class FakeSearchResponse:
        def __init__(self) -> None:
            self.results = [
                FakeSearchResult(
                    url="https://example.com/a",
                    title="Example A",
                    favicon="https://example.com/favicon.ico",
                    highlights=["private highlight"],
                ),
                FakeSearchResult(
                    url="https://example.com/b",
                    title="Example B",
                    highlights=["another private highlight"],
                ),
            ]
            self.cost_dollars = {"total": 1}

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
                    "data": {"output": FakeSearchResponse()},
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
                "thread_id": "thread-web-search-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-web-search-summary", '
        '"tool_name": "web_search_exa", "output": [{"url": "https://example.com/a", '
        '"title": "Example A", "favicon": "https://example.com/favicon.ico"}, '
        '{"url": "https://example.com/b", "title": "Example B"}]}'
        in response.text
    )
    assert "private highlight" not in response.text
    assert "cost_dollars" not in response.text


def test_ai_chat_stream_endpoint_summarizes_find_similar_tool_output(
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
                    "name": "find_similar_exa",
                    "data": {
                        "output": {
                            "results": [
                                {
                                    "url": "https://example.com/similar",
                                    "title": "Similar Page",
                                    "favicon": "https://example.com/favicon.ico",
                                    "text": "private page text",
                                    "score": 0.98,
                                }
                            ],
                            "cost_dollars": {"total": 1},
                        }
                    },
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
                "thread_id": "thread-find-similar-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-find-similar-summary", '
        '"tool_name": "find_similar_exa", "output": [{"url": "https://example.com/similar", '
        '"title": "Similar Page", "favicon": "https://example.com/favicon.ico"}]}'
        in response.text
    )
    assert "private page text" not in response.text
    assert "cost_dollars" not in response.text


def test_ai_chat_stream_endpoint_summarizes_search_tool_message_text_output(
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
                            content=(
                                "Title: Example A\n"
                                "URL: https://example.com/a\n"
                                "ID: result-a\n"
                                "Favicon: https://example.com/favicon.ico\n"
                                "Highlights: ['private highlight']\n\n"
                                "Title: Example B\n"
                                "URL: https://example.com/b\n"
                                "ID: result-b\n"
                                "Favicon: None\n"
                                "Text: private page text"
                            ),
                            tool_call_id="call-1",
                            name="web_search_exa",
                            status="success",
                        )
                    },
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
                "thread_id": "thread-search-text-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-search-text-summary", '
        '"tool_name": "web_search_exa", "output": [{"url": "https://example.com/a", '
        '"title": "Example A", "favicon": "https://example.com/favicon.ico"}, '
        '{"url": "https://example.com/b", "title": "Example B"}]}'
        in response.text
    )
    assert "private highlight" not in response.text
    assert "private page text" not in response.text


def test_ai_chat_stream_endpoint_summarizes_mcp_web_search_text_blocks(
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
                    "name": "web_search",
                    "data": {
                        "output": [
                            {
                                "type": "text",
                                "text": (
                                    "Title: MCP Example A\n"
                                    "URL: https://example.com/mcp-a\n"
                                    "Favicon: https://example.com/favicon.ico\n"
                                    "Text: private page text\n\n"
                                    "Title: MCP Example B\n"
                                    "URL: https://example.com/mcp-b\n"
                                    "Favicon: None"
                                ),
                            }
                        ]
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-mcp-web-search-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-mcp-web-search-summary", '
        '"tool_name": "web_search", "output": [{"url": "https://example.com/mcp-a", '
        '"title": "MCP Example A", "favicon": "https://example.com/favicon.ico"}, '
        '{"url": "https://example.com/mcp-b", "title": "MCP Example B"}]}'
        in response.text
    )
    assert "private page text" not in response.text


def test_ai_chat_stream_endpoint_summarizes_web_search_json_string_output(
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
                    "name": "web_search",
                    "data": {
                        "output": (
                            '[{"url": "https://example.com/json", '
                            '"title": "JSON Result", '
                            '"favicon": "https://example.com/favicon.ico", '
                            '"text": "private page text"}]'
                        )
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-web-search-json-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-web-search-json-summary", '
        '"tool_name": "web_search", "output": [{"url": "https://example.com/json", '
        '"title": "JSON Result", "favicon": "https://example.com/favicon.ico"}]}'
        in response.text
    )
    assert "private page text" not in response.text


def test_ai_chat_stream_endpoint_summarizes_wrapped_exa_json_outputs(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    wrapped_outputs = [
        (
            "web_search_exa",
            "thread-wrapped-web-search",
            {
                "query": "private search query",
                "results": [
                    {
                        "rank": 1,
                        "url": "https://example.com/search",
                        "title": "Wrapped Search",
                        "favicon": "https://example.com/search.ico",
                        "text": "private search text",
                        "highlights": ["private search highlight"],
                    }
                ],
            },
            (
                '"tool_name": "web_search_exa", "output": '
                '[{"url": "https://example.com/search", '
                '"title": "Wrapped Search", '
                '"favicon": "https://example.com/search.ico"}]'
            ),
        ),
        (
            "web_fetch_exa",
            "thread-wrapped-web-fetch",
            {
                "fetch": ["https://example.com/fetch"],
                "results": [
                    {
                        "index": 0,
                        "url": "https://example.com/fetch",
                        "title": "Wrapped Fetch",
                        "favicon": "https://example.com/fetch.ico",
                        "text": "private fetch text",
                    }
                ],
            },
            (
                '"tool_name": "web_fetch_exa", "output": '
                '[{"url": "https://example.com/fetch", '
                '"title": "Wrapped Fetch", '
                '"favicon": "https://example.com/fetch.ico"}]'
            ),
        ),
        (
            "find_similar_exa",
            "thread-wrapped-find-similar",
            {
                "url": "https://example.com/source",
                "results": [
                    {
                        "rank": 1,
                        "url": "https://example.com/similar-wrapped",
                        "title": "Wrapped Similar",
                        "favicon": "https://example.com/similar.ico",
                        "score": 0.98,
                        "text": "private similar text",
                    }
                ],
            },
            (
                '"tool_name": "find_similar_exa", "output": '
                '[{"url": "https://example.com/similar-wrapped", '
                '"title": "Wrapped Similar", '
                '"favicon": "https://example.com/similar.ico"}]'
            ),
        ),
    ]

    with TestClient(app) as client:
        selection_id = _create_model_selection(client)

        for tool_name, thread_id, tool_output, expected_summary in wrapped_outputs:

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
                        "name": tool_name,
                        "data": {
                            "output": json.dumps(tool_output, ensure_ascii=False)
                        },
                    }
                    yield {
                        "event": "on_chain_end",
                        "data": {"output": {"messages": [AIMessage(content="done")]}}
                    }

            client.app.state.supervisor_agent = FakeSupervisorAgent()

            response = client.post(
                "/ai/chat/stream",
                json={
                    "selection_id": selection_id,
                    "prompt": "hello",
                    "thread_id": thread_id,
                },
            )

            assert response.status_code == 200
            assert expected_summary in response.text
            assert "private search query" not in response.text
            assert "private search text" not in response.text
            assert "private search highlight" not in response.text
            assert "private fetch text" not in response.text
            assert "private similar text" not in response.text
            assert '"rank"' not in response.text
            assert '"index"' not in response.text
            assert '"score"' not in response.text
            if tool_name == "find_similar_exa":
                assert "https://example.com/source" not in response.text


def test_ai_chat_stream_endpoint_summarizes_single_web_search_result_object(
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
                    "name": "web_search",
                    "data": {
                        "output": {
                            "url": "https://example.com/single",
                            "title": "Single Result",
                            "favicon": "https://example.com/favicon.ico",
                            "text": "private page text",
                        }
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-web-search-single-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-web-search-single-summary", '
        '"tool_name": "web_search", "output": [{"url": "https://example.com/single", '
        '"title": "Single Result", "favicon": "https://example.com/favicon.ico"}]}'
        in response.text
    )
    assert "private page text" not in response.text


def test_ai_chat_stream_endpoint_returns_search_empty_marker_instead_of_empty_list(
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
                    "name": "web_search",
                    "data": {"output": []},
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-web-search-empty-marker",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-web-search-empty-marker", '
        '"tool_name": "web_search", "output": {"message": "未提取到可展示的搜索链接"}}'
        in response.text
    )
    assert '"output": []' not in response.text


def test_ai_chat_stream_endpoint_summarizes_web_fetch_tool_output(
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
                    "name": "web_fetch_exa",
                    "data": {
                        "output": (
                            "[Result(url='https://api-docs.deepseek.com/zh-cn/', "
                            "title='DeepSeek API Docs', "
                            "favicon='https://api-docs.deepseek.com/favicon.ico', "
                            "text='private page text')]"
                        )
                    },
                }
                yield {
                    "event": "on_chain_end",
                    "data": {"output": {"messages": [AIMessage(content="done")]}}
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-web-fetch-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-web-fetch-summary", '
        '"tool_name": "web_fetch_exa", "output": '
        '[{"url": "https://api-docs.deepseek.com/zh-cn/", '
        '"title": "DeepSeek API Docs", '
        '"favicon": "https://api-docs.deepseek.com/favicon.ico"}]}'
        in response.text
    )
    assert "private page text" not in response.text


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
            headers={"Accept-Language": "en-US"},
        )

    assert response.status_code == 200
    assert response.headers["content-language"] == "en-US"
    assert (
        'event: interrupt\ndata: {"thread_id": "thread-interrupt", "type": "error", "message": "The model call failed.", "id": "interrupt-1"}'
        in response.text
    )
    assert "event: final" not in response.text


def test_ai_chat_stream_endpoint_returns_query_interrupt_choices(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    class FakeInterrupt:
        def __init__(self) -> None:
            self.value = {
                "type": "query",
                "question": "下一步要怎么处理？",
                "firstChoice": "使用推荐方案",
                "firstChoiceDescription": "按系统推荐的完整方案继续推进。",
                "secondChoice": "只做后端",
                "secondChoiceDescription": "只处理后端协议和测试。",
                "thirdChoice": "暂不处理",
                "thirdChoiceDescription": "先暂停这次调整。",
            }
            self.id = "interrupt-query"

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
                "thread_id": "thread-query-interrupt",
            },
        )

    assert response.status_code == 200
    assert (
        'event: interrupt\ndata: {"thread_id": "thread-query-interrupt", "type": "query", "message": null, '
        '"question": "下一步要怎么处理？", "firstChoice": "使用推荐方案", '
        '"firstChoiceDescription": "按系统推荐的完整方案继续推进。", '
        '"secondChoice": "只做后端", "secondChoiceDescription": "只处理后端协议和测试。", '
        '"thirdChoice": "暂不处理", "thirdChoiceDescription": "先暂停这次调整。", '
        '"id": "interrupt-query"}'
        in response.text
    )
    assert "event: final" not in response.text


def test_ai_chat_stream_endpoint_suppresses_query_interrupt_tool_error(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    class FakeInterrupt:
        def __init__(self) -> None:
            self.value = {
                "type": "query",
                "question": "下一步要怎么处理？",
                "firstChoice": "使用推荐方案",
                "firstChoiceDescription": "按系统推荐的完整方案继续推进。",
                "secondChoice": "只做后端",
                "secondChoiceDescription": "只处理后端协议和测试。",
                "thirdChoice": "暂不处理",
                "thirdChoiceDescription": "先暂停这次调整。",
            }
            self.id = "interrupt-query"

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
                    "name": "query",
                    "data": {
                        "input": {
                            "question": "下一步要怎么处理？",
                            "firstChoice": "使用推荐方案",
                            "firstChoiceDescription": "按系统推荐的完整方案继续推进。",
                            "secondChoice": "只做后端",
                            "secondChoiceDescription": "只处理后端协议和测试。",
                            "thirdChoice": "暂不处理",
                            "thirdChoiceDescription": "先暂停这次调整。",
                        }
                    },
                }
                yield {
                    "event": "on_tool_error",
                    "name": "query",
                    "data": {
                        "error": (
                            "(Interrupt(value={'type': 'query', "
                            "'question': '下一步要怎么处理？'}, id='interrupt-query'),)"
                        )
                    },
                }
                yield {
                    "event": "on_chain_stream",
                    "data": {"chunk": {"__interrupt__": (FakeInterrupt(),)}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "prompt": "hello",
                "thread_id": "thread-query-filtered-tool-error",
            },
        )

    assert response.status_code == 200
    assert "event: tool_error" not in response.text
    assert (
        'event: interrupt\ndata: {"thread_id": "thread-query-filtered-tool-error", '
        '"type": "query", "message": null, "question": "下一步要怎么处理？"'
        in response.text
    )


def test_ai_chat_stream_endpoint_summarizes_query_tool_output(
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
                    "name": "query",
                    "data": {
                        "output": ToolMessage(
                            content=json.dumps(
                                {
                                    "choice": "other",
                                    "note": "先补充说明。",
                                },
                                ensure_ascii=False,
                            ),
                            artifact={
                                "question": "下一步要怎么处理？",
                                "firstChoice": "使用推荐方案",
                                "firstChoiceDescription": "按系统推荐的完整方案继续推进。",
                                "secondChoice": "只做后端",
                                "secondChoiceDescription": "只处理后端协议和测试。",
                                "thirdChoice": "暂不处理",
                                "thirdChoiceDescription": "先暂停这次调整。",
                                "internal": "should be hidden",
                            },
                            tool_call_id="call-query",
                            name="query",
                        )
                    },
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
                "thread_id": "thread-query-summary",
            },
        )

    assert response.status_code == 200
    assert (
        'event: tool_end\ndata: {"thread_id": "thread-query-summary", "tool_name": "query", '
        '"output": {"question": "下一步要怎么处理？", "choice": "other", "note": "先补充说明。", '
        '"firstChoice": "使用推荐方案", "firstChoiceDescription": "按系统推荐的完整方案继续推进。", '
        '"secondChoice": "只做后端", "secondChoiceDescription": "只处理后端协议和测试。", '
        '"thirdChoice": "暂不处理", "thirdChoiceDescription": "先暂停这次调整。"}}'
        in response.text
    )
    assert "should be hidden" not in response.text


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
    assert config == {
        "configurable": {"thread_id": "thread-retry"},
        "recursion_limit": 100,
    }
    assert version == "v2"
    assert 'event: final\ndata: {"thread_id": "thread-retry", "content": "retried response"}' in response.text


def test_ai_chat_stream_endpoint_resumes_query_command(
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
                    "data": {"output": {"messages": [AIMessage(content="query resumed")]}},
                }

        client.app.state.supervisor_agent = FakeSupervisorAgent()

        response = client.post(
            "/ai/chat/stream",
            json={
                "selection_id": selection_id,
                "thread_id": "thread-query",
                "command": {
                    "type": "query",
                    "choice": "firstChoice",
                    "note": "按推荐方案继续。",
                },
            },
        )

    assert response.status_code == 200
    agent_input, config, version = seen[0]
    assert isinstance(agent_input, Command)
    assert agent_input.resume == {
        "choice": "firstChoice",
        "note": "按推荐方案继续。",
    }
    assert config == {
        "configurable": {"thread_id": "thread-query"},
        "recursion_limit": 100,
    }
    assert version == "v2"
    assert 'event: final\ndata: {"thread_id": "thread-query", "content": "query resumed"}' in response.text


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
            headers={"Accept-Language": "en-US"},
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
    assert "reasoning_done" in stream_operation["responses"]["200"]["description"]
    assert "url, title, and favicon" in stream_operation["responses"]["200"]["description"]
    assert "retry" in stream_operation["description"]
    assert "query" in stream_operation["description"]
    assert "choice/note" in stream_operation["description"]
    assert "question" in stream_operation["responses"]["200"]["description"]
    assert "firstChoice" in stream_operation["responses"]["200"]["description"]
    assert "firstChoiceDescription" in stream_operation["responses"]["200"]["description"]
    assert "secondChoiceDescription" in stream_operation["responses"]["200"]["description"]
    assert "thirdChoiceDescription" in stream_operation["responses"]["200"]["description"]


def test_ai_chat_history_openapi_documents_history_endpoints(
    temporary_app_config: Config,
) -> None:
    app = create_app(temporary_app_config)

    with TestClient(app) as client:
        payload = client.get("/openapi.json").json()

    assert "/ai/chats" in payload["paths"]
    assert "/ai/chats/{thread_id}/history" in payload["paths"]
    assert "delete" in payload["paths"]["/ai/chats/{thread_id}"]
    assert payload["paths"]["/ai/chats"]["get"]["summary"] == "List AI conversation history"
    assert payload["paths"]["/ai/chats/{thread_id}"]["delete"]["summary"] == "Delete AI conversation history"
    assert (
        payload["paths"]["/ai/chats/{thread_id}/history"]["get"]["summary"]
        == "Get AI conversation history"
    )
    history_message_schema = payload["components"]["schemas"]["AIChatHistoryMessage"]
    assert "reasoning_duration_ms" in history_message_schema["properties"]
    history_summary_schema = payload["components"]["schemas"]["AIChatHistorySummary"]
    assert "context_compacted" in history_summary_schema["properties"]


def test_base_command_accepts_retry_without_prompt() -> None:
    command: BaseCommand = {"type": "retry"}

    assert command["type"] == "retry"
    assert "prompt" not in command


def test_base_command_accepts_query_choice() -> None:
    command: BaseCommand = {
        "type": "query",
        "choice": "firstChoice",
        "note": "按推荐方案继续。",
    }

    assert command["type"] == "query"
    assert command["choice"] == "firstChoice"
    assert command["note"] == "按推荐方案继续。"


async def test_get_all_tools_builds_exa_tools_from_config() -> None:
    config = Config(exa_api_key="test-exa-key")

    tools = await get_all_tools(config)

    assert [tool.name for tool in tools] == [
        "web_search",
        "web_fetch",
        "find_similar",
        "query",
    ]
