import asyncio
from copy import copy
from dataclasses import replace
from time import perf_counter
from typing import override
from uuid import uuid4

from langchain.tools import BaseTool, ToolRuntime
from langchain_core.messages import BaseMessage, ToolCall, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

from agent.interactions import InteractionContext, ask_user, interaction_context
from exceptions import AgentStateError, ModelCallExecutionError
from schemas.config.base import Config
from utils.custom_events import _adispatch_custom_event_safely
from utils.json import jsonify
from utils.logger import logger

from ..base import BaseAgentState, BaseGraph, InputRequest
from ..compaction import (
    CompactionRequest,
    Compactor,
    ContextBudgetPolicy,
    ContextCompactionError,
    DefaultContextBudgetPolicy,
    model_messages_for_state,
)
from ..events import ModelCallErrorEvent, ModelLoadErrorEvent, ToolCallErrorEvent
from ..models import load_chat_model
from ..prompts import (
    PromptBuilder,
    PromptMessageBuilder,
    Prompts,
    normalize_system_prompts,
)
from ..tools.base import Tools, ToolsBuilder, normalize_tools, resolve_tools


def _message_reasoning_content(message: BaseMessage) -> str:
    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return ""

    reasoning_content = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        return reasoning_content
    return ""


def _record_reasoning_duration(message: BaseMessage, duration_ms: int) -> bool:
    if not _message_reasoning_content(message):
        return False

    additional_kwargs = getattr(message, "additional_kwargs", None)
    if not isinstance(additional_kwargs, dict):
        return False

    additional_kwargs["reasoning_duration_ms"] = duration_ms
    return True


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

        if tool and tool.return_direct:
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
        self.context_budget_policy = (
            context_budget_policy
            if context_budget_policy is not None
            else DefaultContextBudgetPolicy(self.config.context_compaction)
        )

        prompts = normalize_system_prompts(system_prompts)
        self.system_prompts = prompts if callable(prompts) else lambda runtime: prompts

    @staticmethod
    def _resolve_model_selection(state: State):
        model_selection = state.get("model")
        if callable(model_selection):
            return model_selection(state=state)
        return model_selection

    async def _prepare_context_node(self, state: State) -> State:
        """Prepare and checkpoint the Supervisor model view before inference."""

        if self.compactor is None:
            return {
                "context_compaction_error": None,
                "context_compaction_event_pending": False,
            }  # type: ignore[return-value]

        try:
            context = interaction_context.get()
            if context and context.resolve_model and context.source == "supervisor":
                state = copy(state)
                state["model"] = await context.resolve_model()
            model_selection = self._resolve_model_selection(state)
            tools = await resolve_tools(self.tools, self.get_runtime(state))
            system_prompts = self.system_prompts(self.get_runtime(state))
            budget = self.context_budget_policy.resolve(model_selection)  # type: ignore[arg-type]
            result = await self.compactor.acompact(
                CompactionRequest(
                    runtime=self.get_runtime(state),
                    system_prompts=tuple(system_prompts),
                    tools=tuple(tools),
                    budget=budget,
                )
            )
        except ContextCompactionError as error:
            message = f"Context compaction failed: {error}"
            logger.error(message)
            update: dict[str, object] = {
                "context_compaction_error": message,
                "context_compaction_event_pending": False,
            }
            if error.partial_result is not None:
                update["context_compaction"] = error.partial_result.build_snapshot()
            return update  # type: ignore[return-value]
        except Exception as error:
            message = f"Context compaction failed: {error}"
            logger.error(message)
            return {
                "context_compaction_error": message,
                "context_compaction_event_pending": False,
            }  # type: ignore[return-value]

        update: dict[str, object] = {
            "context_compaction_error": None,
            "context_compaction_event_pending": result.auto_compacted_this_run,
        }
        if result.should_persist_snapshot:
            update["context_compaction"] = result.build_snapshot()

        logger.debug(
            lambda: (
                "Context compaction completed: "
                f"original_tokens={result.original_tokens}, "
                f"compacted_tokens={result.compacted_tokens}, "
                f"available_input_tokens={budget.available_input_tokens}, "
                f"applied_layers={result.applied_layers}, "
                f"original_messages={len(state.get('messages', []))}, "
                f"model_messages={len(result.model_messages)}"
            )
        )
        if result.warnings:
            logger.warning(f"Context compaction warnings: {result.warnings}")
        return update  # type: ignore[return-value]

    async def _context_compaction_complete_node(self, state: State) -> State:
        if state.get("context_compaction_event_pending"):
            await _adispatch_custom_event_safely(
                "on_context_compaction",
                {"phase": "completed"},
            )
        return {"context_compaction_event_pending": False}  # type: ignore[return-value]

    async def _context_compaction_error_node(self, state: State) -> State:
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
        await ask_user(InputRequest(type="error", message=message))
        return {"context_compaction_error": None}  # type: ignore[return-value]

    @staticmethod
    def _route_after_context_compaction(state: State) -> str:
        if state.get("context_compaction_error"):
            return "error"
        return "complete" if state.get("context_compaction_event_pending") else "model"

    async def _tool_node(
        self,
        state: State,
        runtime: Runtime[InteractionContext | None],
        config: RunnableConfig | None = None,
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
            tools = await resolve_tools(self.tools, self.get_runtime(state))
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

    async def _model_call_node(self, state: State) -> State:
        """
        Model call node. This node is responsible for calling the model and getting the response.
        It switchs the model based on the state.model and calls the model with the state.messages.
        """

        while True:
            context = interaction_context.get()
            if context and context.resolve_model and context.source == "supervisor":
                state = copy(state)
                state["model"] = await context.resolve_model()
            model_selection = self._resolve_model_selection(state)
            try:
                tools = await resolve_tools(self.tools, self.get_runtime(state))
                system_prompts = self.system_prompts(self.get_runtime(state))
                model = load_chat_model(model_selection).bind_tools(tools)

                break
            except Exception as e:
                msg = f"Error loading model:\n{e}"
                logger.error(msg)

                await _adispatch_custom_event_safely(
                    "on_model_load_error",
                    ModelLoadErrorEvent(
                        error=msg,
                        model=model_selection,  # type: ignore
                    ),
                )

                await ask_user(InputRequest(type="error", message=msg))

                continue

        model_input = [
            *system_prompts,
            *(
                model_messages_for_state(state)
                if self.compactor is not None
                else state.get("messages", [])
            ),
        ]

        logger.debug(
            lambda: (
                f"Calling model {getattr(model_selection, 'name', 'unknown')} with input messages:\n{jsonify(model_input)}"
            )
        )

        while True:
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                try:
                    started_at = perf_counter()

                    response = await model.ainvoke(model_input)

                    duration_ms = max(0, round((perf_counter() - started_at) * 1000))
                    if _record_reasoning_duration(response, duration_ms):
                        await _adispatch_custom_event_safely(
                            "on_reasoning_done",
                            {"duration_ms": duration_ms},
                        )
                    context = interaction_context.get()
                    if context and context.source == "supervisor":
                        context.messages.append(response)
                    return {"messages": [response]}  # type: ignore
                except Exception as e:
                    await _adispatch_custom_event_safely(
                        "on_model_call_error",
                        ModelCallErrorEvent(
                            error=str(e), attempt=_ + 1, max_attempts=max_retries
                        ),
                    )
                    logger.error(
                        f"Error calling model, retries in progress {_ + 1}/{max_retries}:\n{e}"
                    )

            logger.error(f"Model call failed after {max_retries} retries.")

            await ask_user(
                InputRequest(
                    type="error",
                    message=f"Model call failed after {max_retries} retries.",
                )
            )

            continue

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
        graph.add_node("model", self._model_call_node)
        graph.add_node("tool", self._tool_node)  # type: ignore
        if self.compactor is not None:
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
