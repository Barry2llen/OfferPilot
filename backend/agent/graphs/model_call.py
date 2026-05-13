
import asyncio
from time import perf_counter

from langgraph.types import interrupt
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, ToolCall, BaseMessage
from langchain_core.callbacks.manager import adispatch_custom_event

from ..models import load_chat_model
from ..tools.base import Tools, ToolsBuilder, normalize_tools, resolve_tools
from ..base import (
    BaseGraph,
    BaseAgentState,
    BaseInterupt
)
from ..prompts import (
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
from schemas.command import BaseCommand
from utils.logger import logger


def _is_missing_parent_run_error(error: RuntimeError) -> bool:
    return "parent run id" in str(error)


async def _adispatch_custom_event_safely(name: str, data: object) -> None:
    try:
        await adispatch_custom_event(name, data)
    except RuntimeError as error:
        if not _is_missing_parent_run_error(error):
            raise
        logger.debug(f"Skipping custom event {name}: {error}")


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

class ModelCallGraph(BaseGraph):

    system_prompts: PromptBuilder
    tools: ToolsBuilder

    def __init__(
            self,
            *args,
            system_prompts: Prompts | PromptBuilder | None = None,
            tools: Tools | ToolsBuilder | None = None,
            **kwargs
        ):
        
        super().__init__(*args, **kwargs)
        self.tools = normalize_tools(tools)
        self.system_prompts = normalize_system_prompts(system_prompts)

    async def _tool_node(self, state: BaseAgentState) -> BaseAgentState:
        """
        Tool node. This node is responsible for calling the tool and getting the response.
        It calls the tool with the state.messages and returns the response.
        """
        
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

            logger.debug(f"Calling tool {name}({','.join(f'{k}={v}' for k, v in args.items())})")

            if name not in tools_dict:
                logger.debug(f"Tool {name} not found in provided tools.")
                return ToolMessage(
                    content=f"Tool {name} not found. Please check if you called the correct tool.",
                    tool_call_id=tool_call_id,
                    name=name,
                    status="error",
            )
            
            try:
                result = await tools_dict[name].ainvoke(tool_call)
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

            if isinstance(result, ToolMessage):
                return result

            return ToolMessage(
                content=result,
                tool_call_id=tool_call_id,
                name=name,
            )
        
        results = await asyncio.gather(*(_call_tool(tool_call) for tool_call in tool_calls))
        return BaseAgentState(messages=list(results))

    async def _model_call_node(self, state: BaseAgentState) -> BaseAgentState:
        """
        Model call node. This node is responsible for calling the model and getting the response.
        It switchs the model based on the state.model and calls the model with the state.messages.
        """
        
        while True:
            try:
                tools = await resolve_tools(self.tools, self.get_runtime(state))
                system_prompts = self.system_prompts(self.get_runtime(state))
                
                model_selection = state.get('model')
                if callable(model_selection):
                    model_selection = model_selection(state=state)
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
        
        while True:
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                try:
                    started_at = perf_counter()

                    #logger.debug(f"Invoking model with system prompts '{system_prompts}' and messages:\n{state.get('messages')}")

                    response = await model.ainvoke(system_prompts + state.get('messages', [])) # type: ignore

                    duration_ms = max(0, round((perf_counter() - started_at) * 1000))
                    if _record_reasoning_duration(response, duration_ms):
                        await _adispatch_custom_event_safely(
                            "on_reasoning_done",
                            {"duration_ms": duration_ms},
                        )
                    return BaseAgentState(messages=[response])
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
            
    def _dicide_next_action(self, state: BaseAgentState) -> str:
        """
        Decide next action node. This node is responsible for deciding the next action based on the state.messages.
        """

        messages = state.get("messages")

        if not messages:
            logger.error("No messages in state, this should not happen.")
            raise AgentStateError("No messages in state, this should not happen.")
        
        if messages[-1].type != 'ai':
            logger.error("Last message is not from AI, this should not happen.")
            raise AgentStateError("Last message is not from AI, this should not happen.")
        
        tool_calls = getattr(messages[-1], 'tool_calls', None) or []
        return 'tool' if tool_calls else 'end'
            
    def get_graph(self) -> StateGraph[BaseAgentState]:
        
        graph = StateGraph[BaseAgentState](BaseAgentState)
        graph.add_node('model', self._model_call_node)
        graph.add_node('tool', self._tool_node)
        graph.add_edge(START, 'model')
        graph.add_edge('tool', 'model')
        graph.add_conditional_edges(
            'model',
            self._dicide_next_action,
            {
                'tool': 'tool',
                'end': END
            }
        )

        return graph

__all__ = [
    "ModelCallGraph"
]
