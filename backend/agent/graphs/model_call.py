
import asyncio
from uuid import uuid4
from time import perf_counter
from typing import override

from langgraph.runtime import Runtime
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import ToolMessage, ToolCall, BaseMessage

from ..models import load_chat_model
from ..compaction import (
    ContextCompactionError,
    CompactionRequest,
    Compactor,
    ContextBudgetPolicy,
    DefaultContextBudgetPolicy,
    model_messages_for_state,
)
from ..tools.base import Tools, ToolsBuilder, normalize_tools, resolve_tools
from ..base import (
    BaseGraph,
    BaseAgentState,
    BaseInterupt
)
from ..prompts import (
    PromptMessageBuilder,
    PromptBuilder,
    Prompts,
    normalize_system_prompts
)
from ..events import (
    ToolCallErrorEvent,
    ModelCallErrorEvent,
    ModelLoadErrorEvent
)
from exceptions import AgentStateError, ModelCallExecutionError
from schemas.config.base import Config
from schemas.command import BaseCommand
from utils.json import jsonify
from utils.logger import logger
from utils.custom_events import _adispatch_custom_event_safely


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

    def _add_interrupt_tool(self, message_id: str, tool_call: ToolCall, tool: BaseTool) -> str:
        logger.debug(
            lambda: f"Tool {tool.name} is an interrupt tool, skip calling it synchronously."
        )
        self._interrupt_tools.append((message_id, tool_call, tool))
        return "[INTERRUPT_TOOL_CALLED]"

    @staticmethod
    def _is_interrupt_tool(tool: BaseTool) -> bool:
        return tool.extras is not None and tool.extras.get("interrupt", False)

    @staticmethod
    def _convert_tool_message(
        result: object,
        tool_call: ToolCall,
        message_id: str | None = None,
        tool: BaseTool | None = None
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
            msg.additional_kwargs.update({
                'return_direct': True
            })

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
        runtime: ToolRuntime[None, State],
    ) -> ToolCall:
        if not (
            ModelCallGraph._schema_has_field(getattr(tool, "args_schema", None), "runtime")
            or ModelCallGraph._schema_has_field(tool.tool_call_schema, "runtime")
        ):
            return tool_call

        logger.debug(
            lambda: f"Injecting runtime into tool call for tool {tool.name}."
        )

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
            **kwargs
        ):
        
        super().__init__(*args, config=config, **kwargs)
        self.tools = normalize_tools(tools)
        self._interrupt_tools: list[tuple[str, ToolCall, BaseTool]] = []
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
            state.get("context_compaction_error")
            or "Context compaction failed."
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
        response: BaseCommand = interrupt(
            BaseInterupt(type="error", message=message)
        )
        if response["type"] == "retry":
            return {"context_compaction_error": None}  # type: ignore[return-value]
        raise ModelCallExecutionError(
            f"{message} Interrupt received with type {response['type']} "
            f"and message {response.get('prompt', '')}"
        )

    @staticmethod
    def _route_after_context_compaction(state: State) -> str:
        if state.get("context_compaction_error"):
            return "error"
        return "complete" if state.get("context_compaction_event_pending") else "model"

    async def _tool_node(
        self,
        state: State,
        runtime: Runtime[None],
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
        
        if messages[-1].type != 'ai':
            logger.warning("Last message is not a tool call, skipping tool node.")
            return state
        
        tool_calls: list[ToolCall] = getattr(messages[-1], 'tool_calls', None) or []
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
            return BaseAgentState(messages=results) # type: ignore

        if not tools:
            logger.warning("No tools provided, skipping tool node.")
            return state

        tools_dict: dict[str, BaseTool] = {tool.name: tool for tool in tools}

        async def _call_tool(tool_call: ToolCall) -> ToolMessage:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call.get("id") or ""

            logger.debug(
                lambda: f"Calling tool {name}({','.join(f'{k}={v}' for k, v in args.items())})"
            )

            if name not in tools_dict:
                logger.debug(
                    lambda: f"Tool {name} not found in provided tools."
                )
                return ToolMessage(
                    content=f"Tool {name} not found. Please check if you called the correct tool.",
                    tool_call_id=tool_call_id,
                    name=name,
                    status="error",
                )

            tool = tools_dict[name]
            injected_tool_call = self._inject_runtime_if_requested(
                tool_call,
                tool,
                ToolRuntime[None, State](
                    state=state,
                    context=runtime.context,
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
                result = (
                    self._add_interrupt_tool(message_id, injected_tool_call, tool)
                    if self._is_interrupt_tool(tool)
                    else await tool.ainvoke(injected_tool_call, config)
                )
            except GraphInterrupt:
                logger.warning(f"Tool {name} raised GraphInterrupt, treating it as an interrupt tool.")
                result = self._add_interrupt_tool(message_id, injected_tool_call, tool)
            except Exception as e:
                logger.error(f"Error calling tool {name} with args {args}: {e}")
                await _adispatch_custom_event_safely("on_tool_call_error", ToolCallErrorEvent(
                    error=str(e),
                    tool_name=name,
                    args=args,
                    tool_call_id=tool_call_id
                ))
                return ToolMessage(
                    content=f"Error calling tool {name} with args {args}: {e}",
                    tool_call_id=tool_call_id,
                    name=name,
                    status="error",
                )
            
            return self._convert_tool_message(result, tool_call, message_id, tool)
        
        results = await asyncio.gather(*(_call_tool(tool_call) for tool_call in tool_calls))
        return {'messages': list(results)} # type: ignore

    async def _exec_interrupt_tool_node(
        self,
        state: State,
        config: RunnableConfig | None = None,
    ) -> State:
        """
        Execute tools that may cause an interrupt one by one.
        """

        if len(self._interrupt_tools) == 0:
            return state

        message_id, tool_call, tool = self._interrupt_tools[-1]
        tool_call_id = tool_call.get("id") or ""

        try:
            result = await tool.ainvoke(tool_call, config)
        except GraphInterrupt:
            raise
        except Exception as e:
            logger.error(f"Error calling interrupt tool {tool.name} with args {tool_call['args']}: {e}")
            await _adispatch_custom_event_safely("on_tool_call_error", ToolCallErrorEvent(
                error=str(e),
                tool_name=tool.name,
                args=tool_call['args'],
                tool_call_id=tool_call_id
            ))
            result = ToolMessage(
                content=f"Error calling interrupt tool {tool.name} with args {tool_call['args']}: {e}",
                tool_call_id=tool_call_id,
                name=tool.name,
                status="error",
            )

        self._interrupt_tools.pop()
        return {
            'messages': [self._convert_tool_message(result, tool_call, message_id, tool)]
        } # type: ignore

    async def _model_call_node(self, state: State) -> State:
        """
        Model call node. This node is responsible for calling the model and getting the response.
        It switchs the model based on the state.model and calls the model with the state.messages.
        """
        
        while True:
            model_selection = self._resolve_model_selection(state)
            try:
                tools = await resolve_tools(self.tools, self.get_runtime(state))
                system_prompts = self.system_prompts(self.get_runtime(state))
                model = load_chat_model(model_selection).bind_tools(tools)

                break
            except Exception as e:
                msg = f"Error loading model:\n{e}"
                logger.error(msg)
                
                await _adispatch_custom_event_safely("on_model_load_error", ModelLoadErrorEvent(
                    error=msg,
                    model=model_selection # type: ignore
                ))

                resp: BaseCommand = interrupt(BaseInterupt(type='error', message=msg))

                if resp['type'] == 'retry':
                    continue
                else:
                    raise ModelCallExecutionError(
                        f"Model loading failed with error: {msg}. Interrupt received with type {resp['type']} and message {resp.get('prompt', '')}"
                    )

        model_input = [
            *system_prompts,
            *(
                model_messages_for_state(state)
                if self.compactor is not None
                else state.get("messages", [])
            ),
        ]

        logger.debug(
            lambda: f"Calling model {getattr(model_selection, 'name', 'unknown')} with input messages:\n{jsonify(model_input)}"
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
                    return {'messages': [response]} # type: ignore
                except Exception as e:
                    await _adispatch_custom_event_safely("on_model_call_error", ModelCallErrorEvent(
                        error=str(e),
                        attempt=_+1,
                        max_attempts=max_retries
                    ))
                    logger.error(f"Error calling model, retries in progress {_+1}/{max_retries}:\n{e}")

            logger.error(f"Model call failed after {max_retries} retries.")

            resp: BaseCommand = interrupt(BaseInterupt(type='error', message=f"Model call failed after {max_retries} retries."))
            
            if resp['type'] == 'retry':
                continue
            else:
                raise ModelCallExecutionError(
                    "Model call failed after "
                    f"{max_retries} retries and code received interrupt with type "
                    f"{resp['type']} and message {resp.get('prompt', '')}"
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
        
        tool_calls = getattr(msg, 'tool_calls', None)

        return 'tool' if tool_calls else 'end'

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
            return_direct = msg.additional_kwargs.get('return_direct')
            if return_direct:
                logger.debug(
                    lambda: "Tool message has return_direct flag, ending the graph."
                )
                return 'end'
            return 'model'
        else:
            logger.error(
                lambda: "Last message in state is not a tool message, this should not happen."
            )
            raise AgentStateError(
                "Last message in state is not a tool message, this should not happen."
            )
            
    @override
    def get_graph(self) -> StateGraph[BaseAgentState]:
        
        graph = StateGraph(BaseAgentState)
        graph.add_node('model', self._model_call_node)
        graph.add_node('tool', self._tool_node) #type: ignore
        graph.add_node('interrupt_tool', self._exec_interrupt_tool_node)
        if self.compactor is not None:
            graph.add_node('compact', self._prepare_context_node)
            graph.add_node('compaction_complete', self._context_compaction_complete_node)
            graph.add_node('compaction_error', self._context_compaction_error_node)
            graph.add_edge(START, 'compact')
            graph.add_conditional_edges(
                'compact',
                self._route_after_context_compaction,
                {
                    'model': 'model',
                    'complete': 'compaction_complete',
                    'error': 'compaction_error',
                },
            )
            graph.add_edge('compaction_complete', 'model')
            graph.add_edge('compaction_error', 'compact')
        else:
            graph.add_edge(START, 'model')
        graph.add_conditional_edges(
            'model',
            self._dicide_next_action,
            {
                'tool': 'tool',
                'end': END
            }
        )
        graph.add_edge('tool', 'interrupt_tool')
        next_model_node = 'compact' if self.compactor is not None else 'model'
        graph.add_conditional_edges(
            'interrupt_tool',
            lambda state: True if len(self._interrupt_tools) > 0 else self._dicide_after_tool(state),
            {
                True: 'interrupt_tool',
                'model': next_model_node,
                'end': END
            }
        )
        

        return graph

__all__ = [
    "ModelCallGraph"
]
