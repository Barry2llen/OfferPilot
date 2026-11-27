import asyncio
from copy import copy
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Annotated, cast, override
from uuid import uuid4

from langchain.tools import BaseTool, ToolRuntime
from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, ToolCall, ToolMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langgraph.channels import UntrackedValue
from langgraph.config import get_config
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command

from agent.interactions import InteractionContext, ask_user, interaction_context
from exceptions import AgentStateError, ModelCallExecutionError
from exceptions.agent import ModelRequestConfigurationError, is_model_bad_request
from schemas.config.base import Config
from schemas.model_selection import ModelSelection
from utils.custom_events import _adispatch_custom_event_safely
from utils.logger import logger
from utils.message_content import extract_message_reasoning
from utils.tool_outputs import ANALYSIS_TOOL_NAMES, is_tool_output_error

from ..base import BaseAgentState, BaseGraph, InputRequest
from ..compaction import (
    ApproximateTokenCounter,
    CompactionRequest,
    Compactor,
    ContextBudgetPolicy,
    ContextCompactionError,
    DefaultContextBudgetPolicy,
    PipelineCompactor,
)
from ..compaction.protection import message_groups, tool_call_names
from ..events import ModelCallErrorEvent, ModelLoadErrorEvent, ToolCallErrorEvent
from ..models import load_chat_model
from ..prompts import (
    PromptBuilder,
    PromptMessageBuilder,
    Prompts,
    normalize_system_prompts,
)
from ..tools.base import Tools, ToolsBuilder, normalize_tools, resolve_tools


def _record_reasoning_duration(message: BaseMessage, duration_ms: int) -> bool:
    if not extract_message_reasoning(message).strip():
        return False

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return False

    additional_kwargs["reasoning_duration_ms"] = duration_ms
    return True


@dataclass(frozen=True, slots=True)
class _PreparedModelCall:
    selection: ModelSelection
    tools: tuple[BaseTool, ...]
    messages: tuple[BaseMessage, ...]


class _PreparedState(BaseAgentState, total=False):
    prepared_model_call: Annotated[_PreparedModelCall | None, UntrackedValue]


class ModelCallGraph[State: BaseAgentState = BaseAgentState](BaseGraph[State]):
    system_prompts: PromptMessageBuilder[State]
    tools: ToolsBuilder[State]

    @staticmethod
    def _convert_tool_message(
        result: object,
        tool_call: ToolCall,
        message_id: str | None = None,
        tool: BaseTool | None = None,
    ) -> ToolMessage:
        if isinstance(result, ToolMessage):
            msg = result
            if message_id and msg.id is None:
                msg.id = message_id
        else:
            msg = ToolMessage(
                id=message_id,
                content=str(result),
                tool_call_id=tool_call.get("id") or "",
                name=tool_call["name"],
            )

        if tool_call["name"] in ANALYSIS_TOOL_NAMES and is_tool_output_error(msg):
            msg.status = "error"

        if tool and tool.return_direct and msg.status != "error":
            msg.additional_kwargs.update({"return_direct": True})

        return msg

    @staticmethod
    def _schema_has_field(schema: object, field_name: str) -> bool:
        model_fields = getattr(schema, "model_fields", None)
        if isinstance(model_fields, dict) and field_name in model_fields:
            return True

        annotations = getattr(schema, "__annotations__", None)
        if isinstance(annotations, dict) and field_name in annotations:
            return True

        if isinstance(schema, dict):
            properties = schema.get("properties")
            if isinstance(properties, dict) and field_name in properties:
                return True

        return False

    @staticmethod
    def _inject_runtime_if_requested(
        tool_call: ToolCall,
        tool: BaseTool,
        runtime: ToolRuntime[InteractionContext | None, State],
    ) -> ToolCall:
        if not (
            ModelCallGraph._schema_has_field(
                getattr(tool, "args_schema", None), "runtime"
            )
            or ModelCallGraph._schema_has_field(tool.tool_call_schema, "runtime")
        ):
            return tool_call

        logger.debug(lambda: f"Injecting runtime into tool call for tool {tool.name}.")

        args = dict(tool_call["args"])
        args["runtime"] = runtime
        return {**tool_call, "args": args}

    def __init__(
        self,
        *args,
        config: Config | None = None,
        system_prompts: Prompts | PromptBuilder[State] | None = None,
        tools: Tools | ToolsBuilder[State] | None = None,
        compactor: Compactor[State] | None = None,
        context_budget_policy: ContextBudgetPolicy | None = None,
        **kwargs,
    ):

        super().__init__(*args, config=config, **kwargs)
        self.tools = normalize_tools(tools)
        self.compactor = compactor
        self.token_counter = (
            compactor.token_counter
            if isinstance(compactor, PipelineCompactor)
            else ApproximateTokenCounter()
        )
        self.context_budget_policy = (
            context_budget_policy
            if context_budget_policy is not None
            else DefaultContextBudgetPolicy(self.config.context_compaction)
        )

        prompts = normalize_system_prompts(system_prompts)
        self.system_prompts = prompts if callable(prompts) else lambda runtime: prompts

    @staticmethod
    def _resolve_model_selection(state: State) -> ModelSelection | None:
        model_selection = state.get("model")
        if callable(model_selection):
            return model_selection(state=state)
        return model_selection

    async def _refresh_model_selection(self, state: State) -> State:
        context = interaction_context.get()
        if (
            context is None
            or context.resolve_model is None
            or context.source != "supervisor"
        ):
            return state
        while True:
            try:
                selection = await context.resolve_model()
                updated = copy(state)
                updated["model"] = selection
                return updated
            except Exception as error:
                logger.exception("Failed to read model configuration")
                await ask_user(InputRequest(type="error", message=str(error)))

    async def _prepare_context_node(self, state: State) -> _PreparedState:
        """Prepare and checkpoint the Supervisor model view before inference."""

        assert self.compactor is not None
        state = await self._refresh_model_selection(state)
        try:
            selection = self._resolve_model_selection(state)
            if selection is None:
                raise ContextCompactionError("Model selection is required.")
            if isinstance(selection, ModelSelection):
                selection = selection.model_copy(deep=True)
            resolved_state = copy(state)
            resolved_state["model"] = selection
            runtime = self.get_runtime(resolved_state)
            tools = tuple(await resolve_tools(self.tools, runtime))
            system_prompts = tuple(self.system_prompts(runtime))
            try:
                budget = self.context_budget_policy.resolve(selection)
            except ValueError as error:
                logger.warning("Invalid context compaction budget: {}", error)
                raise ContextCompactionError(
                    "Invalid model context budget configuration."
                ) from error
            result = await self.compactor.acompact(
                CompactionRequest(
                    runtime=runtime,
                    system_prompts=system_prompts,
                    tools=tools,
                    budget=budget,
                )
            )
            messages = tuple(result.model_messages)
            message_groups(messages)
            tokens = await self.token_counter.acount(
                system_prompts=system_prompts, messages=messages, tools=tools
            )
            if tokens > budget.available_input_tokens:
                raise ContextCompactionError(
                    "Model input exceeds the hard limit with required content preserved."
                )
            prepared = _PreparedModelCall(
                selection, tools, (*system_prompts, *messages)
            )
        except ContextCompactionError as error:
            message = f"Context compaction failed: {error}"
            logger.error(message)
            update: _PreparedState = {
                "context_compaction_error": message,
                "context_compaction_event_pending": False,
                "prepared_model_call": None,
            }
            if error.partial_result is not None:
                update["context_compaction"] = error.partial_result.build_snapshot()
            return update
        except Exception as error:
            message = f"Context compaction failed: Could not prepare the model request ({type(error).__name__})."
            logger.error(message)
            return {
                "context_compaction_error": message,
                "context_compaction_event_pending": False,
                "prepared_model_call": None,
            }

        update = {
            "context_compaction_error": None,
            "context_compaction_event_pending": result.auto_compacted_this_run,
            "prepared_model_call": prepared,
        }
        if result.should_persist_snapshot:
            update["context_compaction"] = result.build_snapshot()

        logger.debug(
            lambda: (
                "Model input verified: "
                f"original_tokens={result.original_tokens}, "
                f"compacted_tokens={tokens}, "
                f"available_input_tokens={budget.available_input_tokens}, "
                f"applied_layers={result.applied_layers}, "
                f"original_messages={len(state.get('messages', []))}, "
                f"model_messages={len(result.model_messages)}"
            )
        )
        if result.warnings:
            logger.debug(f"Context compaction diagnostics: {result.warnings}")
        return update

    async def _context_compaction_complete_node(
        self, state: _PreparedState
    ) -> _PreparedState:
        if state.get("context_compaction_event_pending") and state.get(
            "prepared_model_call"
        ):
            await _adispatch_custom_event_safely(
                "on_context_compaction",
                {"phase": "completed"},
            )
        return {"context_compaction_event_pending": False}

    async def _context_compaction_error_node(self, state: State) -> BaseAgentState:
        message = str(
            state.get("context_compaction_error") or "Context compaction failed."
        )
        await _adispatch_custom_event_safely(
            "on_context_compaction",
            {"phase": "failed"},
        )
        await _adispatch_custom_event_safely(
            "on_model_call_error",
            ModelCallErrorEvent(
                error=message,
                attempt=1,
                max_attempts=1,
            ),
        )
        context = interaction_context.get()
        if context is not None and not context.interactive:
            raise ModelCallExecutionError(message)
        await ask_user(InputRequest(type="error", message=message))
        return {"context_compaction_error": None}

    @staticmethod
    def _route_after_context_compaction(state: State) -> str:
        if state.get("context_compaction_error"):
            return "error"
        return "complete" if state.get("context_compaction_event_pending") else "model"

    async def _tool_node(
        self,
        state: State,
        runtime: Runtime[InteractionContext | None] | Runtime[None],
        config: RunnableConfig | None = None,
        *,
        prepared_tools: tuple[BaseTool, ...] | None = None,
    ) -> State:
        """
        Tool node. This node is responsible for calling the tool and getting the response.
        It calls the tool with the state.messages and returns the response.
        """

        config = config or {}
        messages = state.get("messages")

        if not messages:
            logger.warning("No messages in state, skipping tool node.")
            return state

        if messages[-1].type != "ai":
            logger.warning("Last message is not a tool call, skipping tool node.")
            return state

        tool_calls: list[ToolCall] = getattr(messages[-1], "tool_calls", None) or []
        if not tool_calls:
            logger.warning("Last AI message has no tool calls, skipping tool node.")
            return state

        try:
            tools = (
                prepared_tools
                if prepared_tools is not None
                else await resolve_tools(self.tools, self.get_runtime(state))
            )
        except Exception as e:
            logger.error(f"Error resolving tools: {e}")
            results = [
                ToolMessage(
                    content=f"Error resolving tools: {e}",
                    tool_call_id=tool_call.get("id") or "",
                    name=tool_call["name"],
                    status="error",
                )
                for tool_call in tool_calls
            ]
            return BaseAgentState(messages=results)  # type: ignore

        if not tools:
            logger.warning("No tools provided, skipping tool node.")
            return state

        tools_dict: dict[str, BaseTool] = {tool.name: tool for tool in tools}

        async def _call_tool(tool_call: ToolCall) -> ToolMessage:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call.get("id") or ""

            logger.debug(
                lambda: (
                    f"Calling tool {name}({','.join(f'{k}={v}' for k, v in args.items())})"
                )
            )

            if name not in tools_dict:
                logger.debug(lambda: f"Tool {name} not found in provided tools.")
                return ToolMessage(
                    content=f"Tool {name} not found. Please check if you called the correct tool.",
                    tool_call_id=tool_call_id,
                    name=name,
                    status="error",
                )

            tool = tools_dict[name]
            context = interaction_context.get()
            injected_tool_call = self._inject_runtime_if_requested(
                tool_call,
                tool,
                ToolRuntime[InteractionContext | None, State](
                    state=state,
                    context=replace(
                        context,
                        tool_call_id=tool_call_id,
                        source=name,
                    )
                    if context is not None
                    else None,
                    tool_call_id=tool_call_id,
                    config=config,
                    stream_writer=runtime.stream_writer,
                    store=runtime.store,
                    execution_info=runtime.execution_info,
                    server_info=runtime.server_info,
                ),
            )

            message_id = str(uuid4())
            try:
                context = interaction_context.get()
                token = (
                    interaction_context.set(
                        replace(context, tool_call_id=tool_call_id, source=name)
                    )
                    if context
                    else None
                )
                try:
                    await _adispatch_custom_event_safely(
                        "on_app_tool_start",
                        {
                            "tool_call_id": tool_call_id,
                            "tool_name": name,
                            "input": args,
                        },
                    )
                    result = await tool.ainvoke(injected_tool_call, config)
                finally:
                    if token is not None:
                        interaction_context.reset(token)
            except (TimeoutError, ModelCallExecutionError):
                raise
            except Exception as e:
                logger.error(f"Error calling tool {name} with args {args}: {e}")
                await _adispatch_custom_event_safely(
                    "on_tool_call_error",
                    ToolCallErrorEvent(
                        error=str(e),
                        tool_name=name,
                        args=args,
                        tool_call_id=tool_call_id,
                    ),
                )
                result = ToolMessage(
                    content=f"Error calling tool {name} with args {args}: {e}",
                    tool_call_id=tool_call_id,
                    name=name,
                    status="error",
                )

            message = self._convert_tool_message(result, tool_call, message_id, tool)
            context = interaction_context.get()
            if context and context.source == "supervisor":
                context.messages.append(message)
            await _adispatch_custom_event_safely(
                "on_app_tool_end",
                {"tool_call_id": tool_call_id, "tool_name": name, "output": message},
            )
            return message

        tasks = [asyncio.create_task(_call_tool(call)) for call in tool_calls]
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return {"messages": list(results)}  # type: ignore

    async def _report_model_load_error(
        self, error: Exception, selection: ModelSelection | None
    ) -> None:
        message = f"Error loading model:\n{error}"
        logger.error(message)
        await _adispatch_custom_event_safely(
            "on_model_load_error",
            ModelLoadErrorEvent(error=message, model=selection),
        )
        await ask_user(InputRequest(type="error", message=message))

    async def _invoke_model(
        self,
        model: Runnable[LanguageModelInput, AIMessage],
        model_input: list[BaseMessage],
    ) -> AIMessage | None:
        max_retries = self.config.model_call_retry_attempts
        for attempt in range(1, max_retries + 1):
            try:
                started_at = perf_counter()
                response = await model.ainvoke(model_input)
            except Exception as error:
                await _adispatch_custom_event_safely(
                    "on_model_call_error",
                    ModelCallErrorEvent(
                        error=str(error), attempt=attempt, max_attempts=max_retries
                    ),
                )
                logger.error(
                    "Model call failed on attempt {}/{} ({}).",
                    attempt,
                    max_retries,
                    type(error).__name__,
                )
                if is_model_bad_request(error):
                    raise ModelRequestConfigurationError(
                        str(getattr(error, "message", error))
                    ) from error
                continue

            duration_ms = max(0, round((perf_counter() - started_at) * 1000))
            if _record_reasoning_duration(response, duration_ms):
                await _adispatch_custom_event_safely(
                    "on_reasoning_done", {"duration_ms": duration_ms}
                )
            context = interaction_context.get()
            if context and context.source == "supervisor":
                context.messages.append(response)
            return response

        message = f"Model call failed after {max_retries} retries."
        logger.error(message)
        await ask_user(InputRequest(type="error", message=message))
        return None

    async def _model_call_node(self, state: State) -> State:
        """Call the model through the original path when compaction is disabled."""
        while True:
            state = await self._refresh_model_selection(state)
            selection = self._resolve_model_selection(state)
            try:
                tools = await resolve_tools(self.tools, self.get_runtime(state))
                prompts = self.system_prompts(self.get_runtime(state))
                model = load_chat_model(selection).bind_tools(tools)
                break
            except Exception as error:
                await self._report_model_load_error(error, selection)

        model_input = [*prompts, *state.get("messages", [])]
        while True:
            response = await self._invoke_model(model, model_input)
            if response is not None:
                return cast(State, {"messages": [response]})

    async def _compacted_model_node(self, state: _PreparedState) -> Command:
        prepared = state.get("prepared_model_call")
        if prepared is None:
            # Checkpoint restore drops runtime-only values and requires a fresh budget check.
            return Command(goto="compact")
        try:
            model = load_chat_model(prepared.selection).bind_tools(list(prepared.tools))
        except Exception as error:
            await self._report_model_load_error(error, prepared.selection)
            return Command(goto="compact")

        response = await self._invoke_model(model, list(prepared.messages))
        if response is None:
            return Command(goto="compact")
        try:
            calls = tool_call_names(response) if isinstance(response, AIMessage) else {}
        except ContextCompactionError as error:
            raise ModelCallExecutionError(
                f"Context compaction failed: {error}"
            ) from error
        return Command(update={"messages": [response]}, goto="tool" if calls else END)

    async def _compacted_tool_node(
        self,
        state: _PreparedState,
        runtime: Runtime[None],
    ) -> State:
        prepared = state.get("prepared_model_call")
        resolved_state = cast(State, state)
        if prepared is not None:
            resolved_state = copy(resolved_state)
            resolved_state["model"] = prepared.selection
        return await self._tool_node(
            resolved_state,
            runtime,
            get_config(),
            prepared_tools=prepared.tools if prepared is not None else None,
        )

    def _dicide_next_action(self, state: State) -> str:
        """
        Decide next action node. This node is responsible for deciding the next action based on the state.messages.
        """

        messages = state.get("messages")

        if not messages:
            logger.error("No messages in state, this should not happen.")
            raise AgentStateError("No messages in state, this should not happen.")

        msg = messages[-1]
        if msg.type not in {"ai", "tool"}:
            logger.error(
                "Last message in state is not an AI or tool message, this should not happen."
            )
            raise AgentStateError(
                "Last message in state is not an AI or tool message, this should not happen."
            )

        tool_calls = getattr(msg, "tool_calls", None)

        return "tool" if tool_calls else "end"

    def _dicide_after_tool(self, state: State) -> str:
        """
        Decide whether to end after tool execution or return to the model.
        """

        messages = state.get("messages")

        if not messages:
            logger.error("No messages in state, this should not happen.")
            raise AgentStateError("No messages in state, this should not happen.")

        msg = messages[-1]
        if msg.type == "tool":
            return_direct = msg.additional_kwargs.get("return_direct")
            if return_direct:
                logger.debug(
                    lambda: "Tool message has return_direct flag, ending the graph."
                )
                return "end"
            return "model"
        else:
            logger.error(
                lambda: (
                    "Last message in state is not a tool message, this should not happen."
                )
            )
            raise AgentStateError(
                "Last message in state is not a tool message, this should not happen."
            )

    @override
    def get_graph(self) -> StateGraph[BaseAgentState]:

        graph = StateGraph(BaseAgentState)
        if self.compactor is not None:
            graph.add_node(
                "model",
                self._compacted_model_node,
                input_schema=_PreparedState,
                destinations=("compact", "tool", END),
            )
            graph.add_node(
                "tool", self._compacted_tool_node, input_schema=_PreparedState
            )
            graph.add_node("compact", self._prepare_context_node)
            graph.add_node(
                "compaction_complete", self._context_compaction_complete_node
            )
            graph.add_node("compaction_error", self._context_compaction_error_node)
            graph.add_edge(START, "compact")
            graph.add_conditional_edges(
                "compact",
                self._route_after_context_compaction,
                {
                    "model": "model",
                    "complete": "compaction_complete",
                    "error": "compaction_error",
                },
            )
            graph.add_edge("compaction_complete", "model")
            graph.add_edge("compaction_error", "compact")
        else:
            graph.add_node("model", self._model_call_node)
            graph.add_node("tool", self._tool_node)  # type: ignore
            graph.add_edge(START, "model")
            graph.add_conditional_edges(
                "model", self._dicide_next_action, {"tool": "tool", "end": END}
            )
        next_model_node = "compact" if self.compactor is not None else "model"
        graph.add_conditional_edges(
            "tool",
            self._dicide_after_tool,
            {"model": next_model_node, "end": END},
        )

        return graph


__all__ = ["ModelCallGraph"]
