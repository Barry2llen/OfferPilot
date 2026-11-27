import json
from base64 import b64decode
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Literal

import httpx
import pytest
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, StructuredTool, tool
from langgraph.checkpoint.memory import InMemorySaver

from agent.agents.supervisor.agent import SupervisorAgent
from agent.base import BaseAgentState, GraphRuntime
from agent.compaction import (
    ApproximateTokenCounter,
    CompactionRequest,
    ContextBudget,
    ContextCompactionError,
    ContextCompactionSummary,
    DefaultContextBudgetPolicy,
    PipelineCompactor,
    build_supervisor_compactor,
    model_messages_for_state,
)
from agent.compaction.layers.auto import _SUMMARY_ENVELOPE, AutoCompactLayer
from agent.compaction.protection import message_groups
from agent.compaction.protocols import ToolSchema
from agent.graphs.model_call import ModelCallGraph
from agent.interactions import (
    InteractionBroker,
    InteractionContext,
    interaction_context,
)
from agent.models.chat import load_chat_model
from agent.models.output_limits import summary_output_selection
from db.engine import DatabaseManager
from db.repositories import ChatFileRepository, ChatThreadFileRepository
from exceptions import ModelCallExecutionError
from schemas.config import Config, ContextCompactionConfig
from schemas.model_provider import ModelProvider
from schemas.model_selection import ModelSelection, ThinkingSettings
from services.chat_file_service import ChatFileService, UploadedChatFile
from utils.chat_attachment_content import ATTACHMENT_LAYOUT_KEY, attachment_content


def selection(
    name: str,
    provider: str = "OpenAI",
    *,
    api_mode: Literal["auto", "responses", "chat_completions"] = "auto",
    extra: dict | None = None,
    vision: bool = False,
) -> ModelSelection:
    return ModelSelection(
        provider=ModelProvider(
            provider=provider,
            name="fake",
            api_key="test-key",
            base_url="https://provider.invalid/v1",
        ),
        model_name=name,
        api_mode=api_mode,
        extra_params=extra or {},
        supports_image_input=vision,
    )


class SummaryResolver:
    def __init__(self, model: ModelSelection) -> None:
        self.model = model

    async def aresolve(self, runtime: GraphRuntime) -> ModelSelection:
        return self.model


def summary() -> ContextCompactionSummary:
    return ContextCompactionSummary(
        primary_request_and_intent="Compare verified Shanghai roles",
        key_context_and_constraints=["Compare roles before taking any action"],
        relevant_resources_and_artifacts=["Lookup result previews"],
        issues_and_resolutions=[],
        progress_and_decisions=["Checked roles against the salary requirement"],
        user_message_summaries=[],
        pending_tasks=["Finish comparing roles"],
        current_work="Verifying the job listings",
        optional_next_step="Compare the matching listings",
    )


def request(
    messages: Sequence[BaseMessage],
    *,
    model: ModelSelection,
    settings: ContextCompactionConfig,
) -> CompactionRequest:
    runtime = GraphRuntime[BaseAgentState](
        state={"model": model, "messages": list(messages)},
        additional_args=(),
        additional_keywords={},
    )
    return CompactionRequest(
        runtime=runtime,
        system_prompts=(),
        tools=(),
        budget=DefaultContextBudgetPolicy(settings).resolve(model),
    )


class FakeSummaryModel:
    def __init__(self, *, fail: bool = False) -> None:
        self.inputs: list[list[BaseMessage]] = []
        self.fail = fail

    async def ainvoke(
        self, messages: list[BaseMessage], *, max_repair_attempts: int
    ) -> ContextCompactionSummary:
        assert max_repair_attempts == 0
        self.inputs.append(messages)
        if self.fail:
            raise RuntimeError("provider unavailable")
        return summary()


def install_summary_model(
    monkeypatch: pytest.MonkeyPatch, model: FakeSummaryModel
) -> None:
    def load(
        selection: ModelSelection, schema: type, *, disable_streaming: bool
    ) -> FakeSummaryModel:
        assert schema is ContextCompactionSummary and disable_streaming
        assert 0 < int(selection.extra_params["max_tokens"]) <= 4000
        return model

    monkeypatch.setattr("agent.compaction.layers.auto.load_structured_model", load)


@pytest.mark.parametrize("existing, expected", [(None, 2000), (1250, 1250)])
async def test_summary_generation_limit_reaches_openai_wire_payload(
    monkeypatch: pytest.MonkeyPatch,
    existing: int | None,
    expected: int,
) -> None:
    bodies: list[dict] = []

    async def send(
        client: httpx.AsyncClient, request: httpx.Request, **kwargs: object
    ) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "test-completion",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": summary().model_dump_json(),
                        },
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    main = selection("main")
    extra = (
        {"n": 2} if existing is None else {"n": 2, "max_completion_tokens": existing}
    )
    summarizer = selection("gpt-4o-mini", api_mode="chat_completions", extra=extra)
    settings = ContextCompactionConfig(
        model_context_windows={
            main.model_name: 40_000,
            summarizer.model_name: 28_000,
        }
    )
    counter = ApproximateTokenCounter()
    assembly_overhead = await counter.acount(
        system_prompts=(),
        messages=(HumanMessage(content=_SUMMARY_ENVELOPE), HumanMessage(content="")),
        tools=(),
    )
    current = HumanMessage(content="c" * (3 * (4_000 - assembly_overhead)))
    compact_request = request(
        [AIMessage(content="h" * 15_000), current], model=main, settings=settings
    )
    pipeline = PipelineCompactor(
        token_counter=counter,
        keep_recent_turns=settings.keep_recent_turns,
        layers=(
            AutoCompactLayer(
                model_resolver=SummaryResolver(summarizer),
                budget_policy=DefaultContextBudgetPolicy(settings),
                token_counter=counter,
            ),
        ),
    )
    result = await pipeline.acompact(compact_request)

    assert len(bodies) == 1
    body = bodies[0]
    assert body["max_completion_tokens"] == expected
    assert body.get("n", 1) == 1
    assert not body.get("tools")
    assert (
        f"at most {expected} total generation tokens" in body["messages"][0]["content"]
    )
    assert set(body["response_format"]["json_schema"]["schema"]["required"]) == set(
        ContextCompactionSummary.model_fields
    )
    assert summarizer.extra_params == extra
    assert result.auto_compacted_this_run
    assert result.model_messages[-1] == current
    assert result.compacted_tokens == await counter.acount(
        system_prompts=(),
        messages=result.model_messages,
        tools=(),
    )
    assert result.compacted_tokens < 6_000


@pytest.mark.parametrize(
    "provider, mode, key",
    [
        ("OpenAI", "responses", "max_output_tokens"),
        ("OpenAI Compatible", "chat_completions", "max_completion_tokens"),
        ("DeepSeek", "auto", "max_tokens"),
        ("Anthropic", "auto", "max_tokens"),
        ("Google", "auto", "max_output_tokens"),
    ],
)
def test_summary_limit_uses_native_provider_parameter(
    provider: str,
    mode: Literal["auto", "responses", "chat_completions"],
    key: str,
) -> None:
    original = selection("test-model", provider, api_mode=mode)
    if provider == "Google":
        original = selection(
            "gemini-2.5-flash",
            provider,
            extra={
                "generationConfig": {"maxOutputTokens": 3_000, "candidateCount": 2},
            },
        )
    elif provider == "Anthropic":
        original = original.model_copy(
            update={
                "thinking": ThinkingSettings(
                    type="budget", value=1024, max_tokens=3000
                ),
            }
        )
    configured = summary_output_selection(original, 2000)
    client = load_chat_model(configured)
    messages = [HumanMessage(content="Please produce a summary.")]
    if provider == "Google":
        payload = getattr(client, "_prepare_request")(messages)
        assert getattr(payload["config"], key) == 2000
        assert payload["config"].candidate_count in (None, 1)
    else:
        payload = getattr(client, "_get_request_payload")(messages)
        assert payload[key] == 2000
        assert set(payload).intersection(
            {"max_tokens", "max_completion_tokens", "max_output_tokens"}
        ) == {key}
    if provider == "Anthropic":
        assert original.thinking is not None and original.thinking.max_tokens == 3000
        assert payload["thinking"]["budget_tokens"] == 1024


async def test_budget_counter_includes_wrapped_messages_tools_and_media() -> None:
    counter = ApproximateTokenCounter()
    user = HumanMessage(content='text with "quotes"\n')
    system = SystemMessage(content="system: " + "中" * 1000)
    prompt_tokens = await counter.acount(system_prompts=(), messages=(user,), tools=())
    system_tokens = await counter.acount(
        system_prompts=(system,), messages=(user,), tools=()
    )
    schema = {
        "name": "lookup",
        "description": "Find roles",
        "parameters": {"type": "object"},
    }
    schema_tokens = await counter.acount(
        system_prompts=(system,), messages=(user,), tools=(schema,)
    )
    image = HumanMessage(
        content=[
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
        ]
    )
    media_tokens = await counter.acount(
        system_prompts=(system,), messages=(user, image), tools=(schema,)
    )
    calls = AIMessage(
        content=[{"type": "text", "text": "working"}],
        tool_calls=[
            {"name": "lookup", "id": "c", "args": {"query": "x" * 1000}},
        ],
    )
    exchange_tokens = await counter.acount(
        system_prompts=(system,),
        messages=(user, image, calls, ToolMessage(content="done", tool_call_id="c")),
        tools=(schema,),
    )
    assert 0 < prompt_tokens < system_tokens < schema_tokens
    assert media_tokens - schema_tokens >= 2048
    assert exchange_tokens - media_tokens >= 1000 // 3


async def test_supervisor_completes_thirty_tool_iterations_within_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_results: dict[str, str] = {}
    seen_inputs: list[list[BaseMessage]] = []
    tool_steps: list[int] = []
    summarizer = FakeSummaryModel()
    install_summary_model(monkeypatch, summarizer)

    @tool(response_format="content_and_artifact")
    def lookup(step: int) -> tuple[str, dict[str, object]]:
        """Return matching jobs for a search page."""
        tool_steps.append(step)
        content = f"Page {step}. " + (
            "Shanghai role, salary floor 20k, compare first. " * 230
        )
        raw_results[f"call-{step}"] = content
        return content, {"page": step, "original": content}

    class LoopModel:
        def bind_tools(self, tools: list[BaseTool]) -> "LoopModel":
            assert tools == [lookup]
            return self

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            step = len(seen_inputs)
            seen_inputs.append(messages)
            if step == 30:
                return AIMessage(content="Finished comparing 30 search pages.")
            return AIMessage(
                content="",
                tool_calls=[
                    {"id": f"call-{step}", "name": lookup.name, "args": {"step": step}},
                ],
            )

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model", lambda _: LoopModel()
    )
    selected = selection("loop-model")
    settings = ContextCompactionConfig(
        model_context_windows={selected.model_name: 40_000}
    )
    saver = InMemorySaver()
    supervisor = SupervisorAgent(
        checkpointer=saver,
        config=Config(context_compaction=settings),
        tools=(lookup,),
        compaction_model_resolver=SummaryResolver(selection("summary-model")),
    ).get_agent()
    user_text = "  只考虑上海，税前月薪不低于 20k，不得编造经历，先比较岗位，不要替我投递\n```\ncondition = 'A&B'\n```  "
    config: RunnableConfig = {
        "configurable": {"thread_id": "thirty-results"},
        "recursion_limit": 180,
    }
    result = await supervisor.ainvoke(
        {"model": selected, "messages": [HumanMessage(content=user_text)]}, config
    )

    assert tool_steps == list(range(30))
    assert len(seen_inputs) == 31
    assert len(result["messages"]) == 62
    assert result["messages"][0].content == user_text
    assert result["messages"][-1].content == "Finished comparing 30 search pages."
    assert len(summarizer.inputs) > 1
    assert settings.keep_recent_turns == 4
    counter = ApproximateTokenCounter()
    actual_sizes = []
    for model_input in seen_inputs:
        assert isinstance(model_input[0], SystemMessage)
        assert model_input[0] == seen_inputs[0][0]
        assert any(
            isinstance(message, HumanMessage) and message.content == user_text
            for message in model_input
        )
        message_groups(model_input)
        actual_sizes.append(
            await counter.acount(
                system_prompts=(), messages=model_input, tools=(lookup,)
            )
        )
    assert max(actual_sizes) <= 10_000
    raw_size = await counter.acount(
        system_prompts=(seen_inputs[0][0],),
        messages=result["messages"][:-1],
        tools=(lookup,),
    )
    assert raw_size > 10_000
    print(
        f"tool loop tokens: raw={raw_size}, peak_sent={max(actual_sizes)}, final_sent={actual_sizes[-1]}, summaries={len(summarizer.inputs)}"
    )

    assert any(
        isinstance(message, ToolMessage)
        and message.tool_call_id == "call-0"
        and len(message.content) <= settings.tool_result_max_characters
        for model_input in seen_inputs
        for message in model_input
    )
    for message in result["messages"]:
        if isinstance(message, ToolMessage):
            assert message.content == raw_results[message.tool_call_id]
            assert message.artifact["original"] == message.content
    for checkpoint in saver.list(None):
        assert "prepared_model_call" not in checkpoint.checkpoint["channel_values"]
        assert all(
            write[1] != "prepared_model_call"
            for write in checkpoint.pending_writes or ()
        )


@pytest.mark.parametrize("initial_size", [9_000, 10_001])
async def test_soft_and_hard_failure_gate_the_real_model_graph(
    monkeypatch: pytest.MonkeyPatch,
    initial_size: int,
) -> None:
    fake = FakeSummaryModel(fail=True)
    install_summary_model(monkeypatch, fake)
    phases: list[str] = []
    seen_inputs: list[list[BaseMessage]] = []

    async def event(name: str, data: dict, *args: object, **kwargs: object) -> None:
        if name == "on_context_compaction":
            phases.append(data["phase"])

    class BusinessModel:
        def bind_tools(self, tools: list[BaseTool]) -> "BusinessModel":
            return self

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            seen_inputs.append(messages)
            return AIMessage(content="done")

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model", lambda _: BusinessModel()
    )
    monkeypatch.setattr("agent.graphs.model_call._adispatch_custom_event_safely", event)
    monkeypatch.setattr(
        "agent.compaction.layers.auto._adispatch_custom_event_safely", event
    )
    model = selection("main")
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 40_000})
    config = Config(context_compaction=settings)
    graph = ModelCallGraph(
        config=config, compactor=build_supervisor_compactor(config)
    ).get_compiled_graph(
        checkpointer=InMemorySaver(),
    )
    run_config: RunnableConfig = {"configurable": {"thread_id": "failed-summary"}}
    counter = ApproximateTokenCounter()
    user = HumanMessage(content="  exact current request\n")
    base_tokens = await counter.acount(
        system_prompts=(), messages=(AIMessage(content=""), user), tools=()
    )
    previous = AIMessage(content="p" * (3 * (initial_size - base_tokens)))
    messages = [previous, user]
    assert (
        await counter.acount(system_prompts=(), messages=messages, tools=())
        == initial_size
    )

    if initial_size > 10_000:
        with pytest.raises(ModelCallExecutionError, match="structured output failed"):
            await graph.ainvoke({"model": model, "messages": messages}, run_config)
        assert not seen_inputs
        state = await graph.aget_state(run_config)
        assert state.values["context_compaction"]["status"] == "pending_auto_compact"
        assert not state.values["context_compaction"]["auto_compacted"]
    else:
        output = await graph.ainvoke({"model": model, "messages": messages}, run_config)
        assert seen_inputs == [messages]
        assert "context_compaction" not in output
    assert len(fake.inputs) == 1
    assert phases == ["started", "failed"]


async def test_runtime_preparation_refreshes_after_user_retry_and_for_next_inference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = [
        selection("first", extra={"max_tokens": 21_000}),
        selection("second", extra={"max_completion_tokens": 22_000}),
        selection("third"),
    ]
    config = Config(
        model_call_retry_attempts=2,
        context_compaction=ContextCompactionConfig(
            model_context_windows={"second": 45_000}
        ),
    )
    resolved: list[ModelSelection] = []
    prompts: list[tuple[str, str]] = []
    toolsets: list[tuple[str, str]] = []
    actual: list[tuple[ModelSelection, str, str, list[BaseMessage]]] = []
    preflight: list[tuple[str, str, tuple[str, ...]]] = []
    budgets: list[tuple[ModelSelection, int]] = []

    class RecordingBudget(DefaultContextBudgetPolicy):
        def resolve(self, model_selection: ModelSelection) -> ContextBudget:
            budget = super().resolve(model_selection)
            budgets.append((model_selection, budget.available_input_tokens))
            return budget

    class Counting(ApproximateTokenCounter):
        async def acount(
            self,
            *,
            system_prompts: Sequence[BaseMessage],
            messages: Sequence[BaseMessage],
            tools: Sequence[ToolSchema],
        ) -> int:
            if system_prompts and isinstance(tools[0], BaseTool):
                preflight.append(
                    (
                        str(system_prompts[0].content),
                        tools[0].name,
                        tuple(str(m.content) for m in messages),
                    )
                )
            return await super().acount(
                system_prompts=system_prompts, messages=messages, tools=tools
            )

    def make_tools(runtime: GraphRuntime) -> tuple[BaseTool]:
        chosen = runtime.state.get("model")
        assert isinstance(chosen, ModelSelection)
        name = f"lookup_{len(toolsets) + 1}"
        toolsets.append((chosen.model_name, name))
        return (
            StructuredTool.from_function(
                lambda: "role", name=name, description="Check a role"
            ),
        )

    def make_prompts(runtime: GraphRuntime) -> SystemMessage:
        chosen = runtime.state.get("model")
        assert isinstance(chosen, ModelSelection)
        prompt = (
            f"System instruction for {chosen.model_name} revision {len(prompts) + 1}"
        )
        prompts.append((chosen.model_name, prompt))
        return SystemMessage(content=prompt)

    class ChangingModel:
        def __init__(self, model: ModelSelection) -> None:
            self.model = model
            self.tool_name = ""

        def bind_tools(self, tools: list[BaseTool]) -> "ChangingModel":
            self.tool_name = tools[0].name
            return self

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            actual.append(
                (self.model, str(messages[0].content), self.tool_name, messages.copy())
            )
            if self.model.model_name == "first":
                raise RuntimeError("business call unavailable")
            return AIMessage(content=self.model.model_name)

    async def resolve() -> ModelSelection:
        selected = models[len(resolved)]
        resolved.append(selected)
        return selected

    async def publish(run_id: str, name: str, data: dict) -> None:
        if name == "input_required":
            assert len(actual) == 2 and len(resolved) == 1
            await broker.submit(run_id, data["request_id"], {"type": "retry"})

    monkeypatch.setattr("agent.graphs.model_call.load_chat_model", ChangingModel)
    fake_summary = FakeSummaryModel()
    install_summary_model(monkeypatch, fake_summary)
    counter = Counting()
    compactor = build_supervisor_compactor(config, token_counter=counter)
    graph = ModelCallGraph(
        config=config,
        tools=make_tools,
        system_prompts=make_prompts,
        compactor=compactor,
        context_budget_policy=RecordingBudget(config.context_compaction),
    ).get_compiled_graph(checkpointer=InMemorySaver())
    broker = InteractionBroker(publish)
    run_config: RunnableConfig = {"configurable": {"thread_id": "dynamic-model"}}
    context = interaction_context.set(
        InteractionContext(broker, "run", "dynamic-model", resolve_model=resolve)
    )
    try:
        # The first request is large enough to summarize once. Its ordinary
        # retry uses the same input, even though the next resolver result differs.
        user = HumanMessage(content="  current instructions\n")
        first = await graph.ainvoke(
            {"model": models[0], "messages": [AIMessage(content="a" * 240_000), user]},
            run_config,
        )
        assert first["messages"][-1].content == "second"
        assert first["context_compaction"]["auto_compacted"]
        await graph.ainvoke(
            {"model": models[2], "messages": [HumanMessage(content="next")]}, run_config
        )
    finally:
        interaction_context.reset(context)

    assert resolved == models
    assert budgets == list(zip(models, (97_000, 13_000, 98_000), strict=True))
    assert len(fake_summary.inputs) == 1
    assert [item[0] for item in actual] == [models[0], models[0], models[1], models[2]]
    assert actual[0] == actual[1]
    assert prompts == [
        (model.model_name, prompt) for model, prompt, _, _ in (actual[0], *actual[2:])
    ]
    assert toolsets == [
        (model.model_name, name) for model, _, name, _ in (actual[0], *actual[2:])
    ]
    for _, prompt, name, sent in actual:
        assert (
            prompt,
            name,
            tuple(str(message.content) for message in sent[1:]),
        ) in preflight


@pytest.fixture
def help_with_chat_files(
    temporary_database_manager: DatabaseManager,
    workspace_tmp_dir: Path,
) -> Iterator[ChatFileService]:
    temporary_database_manager.initialize_tables()
    with temporary_database_manager.session_scope() as session:
        yield ChatFileService(
            ChatFileRepository(session),
            ChatThreadFileRepository(session),
            workspace_tmp_dir,
        )


@pytest.mark.parametrize("as_image", [False, True], ids=["text", "image"])
async def test_supervisor_summarizes_repeated_attachment_references_and_reuses_snapshot(
    help_with_chat_files: ChatFileService,
    monkeypatch: pytest.MonkeyPatch,
    as_image: bool,
) -> None:
    service = help_with_chat_files
    thread_id = "repeated-attachment-references"
    model = selection("main", vision=as_image)
    upload = (
        UploadedChatFile(
            "evidence.png",
            "image/png",
            b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            ),
        )
        if as_image
        else UploadedChatFile("evidence.txt", "text/plain", b"source record\n" * 100)
    )
    uploaded = service.prepare_prompt(
        thread_id=thread_id,
        selection=model,
        prompt="保留原始证据。",
        file_ids=[],
        uploaded_files=[upload],
    )
    evidence = uploaded.human_message.model_copy(update={"id": "upload"})
    layout = attachment_content(evidence)
    assert layout is not None and len(layout.spans) == 1
    assert layout.spans[0]["injection_mode"] == ("image" if as_image else "text")

    def reference(note: str, message_id: str) -> HumanMessage:
        prepared = service.prepare_prompt(
            thread_id=thread_id,
            selection=model,
            prompt=note,
            file_ids=[uploaded.attachments[0].file_id],
            uploaded_files=[],
        )
        message = prepared.human_message.model_copy(update={"id": message_id})
        layout = attachment_content(message)
        assert layout is not None and layout.spans == []
        return message

    notes = [
        "",
        *(f"第 {i} 条限制\n" + "additional requirement " * 700 for i in range(5)),
    ]
    raw_messages: list[BaseMessage] = [evidence, AIMessage(content="Read", id="read")]
    for index, note in enumerate(notes):
        raw_messages.extend(
            [
                reference(note, f"reference-{index}"),
                AIMessage(content="Acknowledged", id=f"answer-{index}"),
            ]
        )
    current_text = "  先核对原件，禁止编造经历。\n\t保留空格和换行。  \n"
    current = reference(current_text, "current")
    raw_messages.append(current)
    original_history = [message.model_copy(deep=True) for message in raw_messages]

    summarizer = FakeSummaryModel()
    install_summary_model(monkeypatch, summarizer)
    seen_inputs: list[list[BaseMessage]] = []

    class BusinessModel:
        def bind_tools(self, tools: list[BaseTool]) -> "BusinessModel":
            assert not tools
            return self

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            seen_inputs.append(messages)
            return AIMessage(content="Checked the source.")

    monkeypatch.setattr(
        "agent.graphs.model_call.load_chat_model", lambda _: BusinessModel()
    )
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 40_000})
    supervisor = SupervisorAgent(
        checkpointer=InMemorySaver(),
        config=Config(context_compaction=settings),
        compaction_model_resolver=SummaryResolver(selection("summary-model")),
    ).get_agent()
    run_config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    counter = ApproximateTokenCounter()
    hard_limit = (
        DefaultContextBudgetPolicy(settings).resolve(model).available_input_tokens
    )

    output = await supervisor.ainvoke(
        {"model": model, "messages": raw_messages}, run_config
    )

    assert len(seen_inputs) == len(summarizer.inputs) == 1
    assert (
        await counter.acount(
            system_prompts=seen_inputs[0][:1], messages=original_history, tools=()
        )
        > hard_limit
    )
    records = json.loads(str(summarizer.inputs[0][1].content))
    assert [
        record["content"] for record in records if record["role"] == "human"
    ] == notes
    snapshot = output["context_compaction"]
    assert snapshot["status"] == "complete" and snapshot["auto_compacted"]
    assert snapshot["source_message_count"] == len(raw_messages)
    assert seen_inputs[0][1:] == snapshot["messages"]
    assert evidence in seen_inputs[0]
    assert seen_inputs[0][-1] == current
    assert seen_inputs[0][-1].additional_kwargs["display_content"] == current_text
    assert not any(
        (message.id or "").startswith("reference-") for message in seen_inputs[0]
    )
    assert raw_messages == original_history == output["messages"][:-1]

    follow_up = reference("\t继续核对原件。\n", "follow-up")
    resumed = await supervisor.ainvoke({"messages": [follow_up]}, run_config)

    assert len(seen_inputs) == 2 and len(summarizer.inputs) == 1
    assert resumed["context_compaction"] == snapshot
    first_answer = output["messages"][-1]
    assert seen_inputs[1][1:] == [*snapshot["messages"], first_answer, follow_up]
    assert resumed["messages"][:-1] == [*original_history, first_answer, follow_up]
    for model_input in seen_inputs:
        assert (
            await counter.acount(system_prompts=(), messages=model_input, tools=())
            <= hard_limit
        )


async def test_equivalent_file_is_removed_only_with_full_payload_in_view(
    help_with_chat_files: ChatFileService,
) -> None:
    service = help_with_chat_files
    model = selection("main")
    note = " requirement\n".ljust(1202, "x") + "禁止编造经历\n`code = 'a&b'`  "
    note = note.ljust(1500, " ")
    first = service.prepare_prompt(
        thread_id="origin",
        selection=model,
        prompt="  \n",
        file_ids=[],
        uploaded_files=[
            UploadedChatFile("portfolio.txt", "text/plain", b"evidence " * 11_400)
        ],
    )
    file_id = first.attachments[0].file_id
    current = service.prepare_prompt(
        thread_id="second",
        selection=model,
        prompt=note,
        file_ids=[file_id],
        uploaded_files=[],
    )
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 75_000})
    config = Config(context_compaction=settings)
    pipeline = build_supervisor_compactor(config)
    assert pipeline is not None
    result = await pipeline.acompact(
        request(
            [first.human_message, current.human_message],
            model=model,
            settings=settings,
        )
    )

    assert result.original_tokens > 45_000
    assert result.compacted_tokens < 36_000
    assert result.applied_layers == ("historical_attachments",)
    assert result.model_messages[-1] == current.human_message
    assert current.human_message.additional_kwargs["display_content"] == note
    assert note.index("禁止编造经历") > 1200
    assert isinstance(current.human_message.content, list)
    visible = current.human_message.content[0]
    assert isinstance(visible, dict)
    assert str(visible["text"]).startswith(note)
    older = result.model_messages[0]
    assert isinstance(older, HumanMessage)
    layout = attachment_content(older)
    assert layout is not None and not layout.spans
    assert older.additional_kwargs["display_content"] == "  \n"
    assert len(first.human_message.content) == 2
    assert len(current.human_message.content) == 2


async def test_snapshot_reuses_summarized_attachment_duplicate_with_exact_copy(
    help_with_chat_files: ChatFileService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = help_with_chat_files
    model = selection("main")
    old_text = "historical requirement " * 1_350
    upload = service.prepare_prompt(
        thread_id="origin",
        selection=model,
        prompt=old_text,
        file_ids=[],
        uploaded_files=[
            UploadedChatFile("evidence.txt", "text/plain", b"exact source")
        ],
    )
    duplicate = service.prepare_prompt(
        thread_id="second",
        selection=model,
        prompt="Use the full evidence.",
        file_ids=[upload.attachments[0].file_id],
        uploaded_files=[],
    )
    older = upload.human_message.model_copy(update={"id": "older"})
    newer = duplicate.human_message.model_copy(update={"id": "newer"})
    raw_messages = [older, newer]
    summarizer = FakeSummaryModel()
    install_summary_model(monkeypatch, summarizer)
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 40_000})
    pipeline = build_supervisor_compactor(Config(context_compaction=settings))
    assert pipeline is not None
    initial_request = request(raw_messages, model=model, settings=settings)

    result = await pipeline.acompact(initial_request)

    assert result.applied_layers == ("historical_attachments", "auto_compact")
    assert len(result.model_messages) == 2 and result.model_messages[-1] == newer
    assert json.loads(str(summarizer.inputs[0][1].content)) == [
        {"role": "human", "content": old_text}
    ]
    snapshot = result.build_snapshot()
    follow_up = HumanMessage(content="Continue.", id="follow-up")
    raw_suffix = [*raw_messages, follow_up]
    assert model_messages_for_state(
        {"messages": raw_suffix, "context_compaction": snapshot}
    ) == [*result.model_messages, follow_up]

    # An old summary cannot stand in for the last exact copy of the attachment.
    without_evidence = {**snapshot, "messages": result.model_messages[:-1]}
    assert (
        model_messages_for_state(
            {"messages": raw_suffix, "context_compaction": without_evidence}
        )
        == raw_suffix
    )


async def test_reference_only_legacy_and_empty_text_keep_unique_evidence(
    help_with_chat_files: ChatFileService,
) -> None:
    service = help_with_chat_files
    model = selection("main")
    first = service.prepare_prompt(
        thread_id="reuse",
        selection=model,
        prompt="",
        file_ids=[],
        uploaded_files=[
            UploadedChatFile("notes.txt", "text/plain", b"evidence " * 11_400)
        ],
    )
    reference = service.prepare_prompt(
        thread_id="reuse",
        selection=model,
        prompt="reuse",
        file_ids=[first.attachments[0].file_id],
        uploaded_files=[],
    )
    legacy = first.human_message.model_copy(
        update={
            "additional_kwargs": {
                key: value
                for key, value in first.human_message.additional_kwargs.items()
                if key != ATTACHMENT_LAYOUT_KEY
            },
        }
    )
    assert len(reference.human_message.content) == 1
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 40_000})
    pipeline = build_supervisor_compactor(Config(context_compaction=settings))
    assert pipeline is not None
    for evidence in (first.human_message, legacy):
        messages = [evidence, reference.human_message]
        with pytest.raises(
            ContextCompactionError, match="no eligible history"
        ) as caught:
            await pipeline.acompact(request(messages, model=model, settings=settings))
        partial = caught.value.partial_result
        assert partial is not None and partial.model_messages == messages
        assert evidence.additional_kwargs["display_content"] == ""
        assert len(evidence.content) == 2


async def test_unique_image_is_kept_even_when_the_same_file_has_ocr(
    help_with_chat_files: ChatFileService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = help_with_chat_files
    monkeypatch.setattr(
        "services.chat_file_service.extract_ocr_text", lambda _: "OCR text"
    )
    vision = selection("vision", vision=True)
    first = service.prepare_prompt(
        thread_id="image",
        selection=vision,
        prompt="",
        file_ids=[],
        uploaded_files=[
            UploadedChatFile("evidence.png", "image/png", b"image evidence")
        ],
    )
    ocr = service.prepare_prompt(
        thread_id="ocr",
        selection=selection("text"),
        prompt="check evidence",
        file_ids=[first.attachments[0].file_id],
        uploaded_files=[],
    )
    settings = ContextCompactionConfig(
        model_context_windows={vision.model_name: 31_000}
    )
    pipeline = build_supervisor_compactor(Config(context_compaction=settings))
    assert pipeline is not None
    messages = [first.human_message, ocr.human_message]
    with pytest.raises(ContextCompactionError, match="no eligible history") as caught:
        await pipeline.acompact(request(messages, model=vision, settings=settings))
    partial = caught.value.partial_result
    assert partial is not None and partial.model_messages == messages
    assert first.human_message.additional_kwargs["display_content"] == ""
    assert isinstance(first.human_message.content, list)
    image = first.human_message.content[1]
    assert isinstance(image, dict) and image["type"] == "image_url"


async def test_overlong_plain_user_text_is_kept_verbatim_and_blocks_the_request(
    help_with_chat_files: ChatFileService,
) -> None:
    model = selection("main")
    prompt = "  \n" + "x" * 32_000 + " 禁止编造经历 \n\n"
    prepared = help_with_chat_files.prepare_prompt(
        thread_id="text",
        selection=model,
        prompt=prompt,
        file_ids=[],
        uploaded_files=[],
    )
    assert prepared.human_message.content == prompt
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 40_000})
    pipeline = build_supervisor_compactor(Config(context_compaction=settings))
    assert pipeline is not None
    with pytest.raises(ContextCompactionError, match="no eligible history") as caught:
        await pipeline.acompact(
            request([prepared.human_message], model=model, settings=settings)
        )
    partial = caught.value.partial_result
    assert partial is not None and partial.model_messages == [prepared.human_message]


async def test_unsupported_summary_adapter_falls_back_without_a_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = selection("main")
    settings = ContextCompactionConfig(model_context_windows={model.model_name: 40_000})
    pipeline = build_supervisor_compactor(
        Config(context_compaction=settings),
        model_resolver=SummaryResolver(selection("unknown", provider="Unknown")),
    )
    assert pipeline is not None
    provider = FakeSummaryModel()
    install_summary_model(monkeypatch, provider)
    messages = [AIMessage(content="x" * 26_500), HumanMessage(content="query")]
    result = await pipeline.acompact(request(messages, model=model, settings=settings))
    assert result.model_messages == messages
    assert any(
        "soft_degraded" in warning and "supported generation-limit adapter" in warning
        for warning in result.warnings
    )
    assert not result.auto_compacted and not provider.inputs
