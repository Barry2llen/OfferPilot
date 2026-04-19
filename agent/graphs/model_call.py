
import asyncio

from typing import (
    Sequence
)

from langgraph.types import interrupt
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage, ToolCall, BaseMessage

from exceptions import AgentStateError, ModelCallExecutionError
from ..models import load_chat_model
from ..state import BaseAgentState
from ..types.interupt import BaseInterupt
from .base import BaseGraph
from schemas.config.base import Config
from schemas.config import load_config
from schemas.command import BaseCommand
from utils.logger import logger


class ModelCallGraph(BaseGraph):

    def __init__(
            self,
            *args,
            system_prompts: list[BaseMessage] | None = None,
            config: Config | None = None,
            tools: Sequence[BaseTool] | None = None,
            **kwargs
        ):
        
        super().__init__(*args, **kwargs)
        self.config = load_config() if config is None else config
        self.tools = tools or tuple[BaseTool]()
        self.tools_dict = {tool.name: tool for tool in self.tools}
        self.system_prompts = system_prompts or []

    async def _tool_node(self, state: BaseAgentState) -> BaseAgentState:
        """
        Tool node. This node is responsible for calling the tool and getting the response.
        It calls the tool with the state.messages and returns the response.
        """

        if not self.tools:
            logger.warning("No tools provided, skipping tool node.")
            return state
        
        messages = state['messages']

        if not messages:
            logger.warning("No messages in state, skipping tool node.")
            return state
        
        if messages[-1].type != 'ai' or not hasattr(messages[-1], 'tool_calls') or not messages[-1].tool_calls:
            logger.warning("Last message is not a tool call, skipping tool node.")
            return state
        
        tool_calls: list[ToolCall] = messages[-1].tool_calls

        async def _call_tool(tool_call: ToolCall) -> ToolMessage:
            name = tool_call["name"]
            args = tool_call["args"]
            tool_call_id = tool_call.get("id") or ""

            if name not in self.tools_dict:
                logger.debug(f"Tool {name} not found in provided tools.")
                return ToolMessage(
                    content=f"Tool {name} not found. Please check if you called the correct tool.",
                    tool_call_id=tool_call_id,
                    name=name,
                    status="error",
            )
            
            try:
                result = await self.tools_dict[name].ainvoke(tool_call)
            except Exception as e:
                logger.error(f"Error calling tool {name} with args {args}: {e}")
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

    def _model_call_node(self, state: BaseAgentState) -> BaseAgentState:
        """
        Model call node. This node is responsible for calling the model and getting the response.
        It switchs the model based on the state.model and calls the model with the state.messages.
        """

        logger.debug(f"Calling model with state: {state}")
        
        try:
            model_selection = state['model']
            if callable(model_selection):
                model_selection = model_selection(state=state)
            model = load_chat_model(model_selection).bind_tools(self.tools)
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            resp: BaseCommand = interrupt(BaseInterupt(type='error', message=f"Error loading model: {e}"))
            return BaseAgentState()
        
        while True:
            max_retries = self.config.model_call_retry_attempts
            for _ in range(max_retries):
                try:
                    logger.debug(f"Invoking model with system prompts: {self.system_prompts} and messages: {state['messages']}")
                    response = model.invoke(self.system_prompts + state['messages'])
                    return BaseAgentState(messages=[response])
                except Exception as e:
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

        messages = state['messages']

        if not messages:
            logger.error("No messages in state, this should not happen.")
            raise AgentStateError("No messages in state, this should not happen.")
        
        if messages[-1].type != 'ai':
            logger.error("Last message is not from AI, this should not happen.")
            raise AgentStateError("Last message is not from AI, this should not happen.")
        
        return 'end' if not hasattr(messages[-1], 'tool_calls') or not messages[-1].tool_calls else 'tool'
            
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
