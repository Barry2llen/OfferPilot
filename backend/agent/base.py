
from __future__ import annotations

from typing import (
    Any,
    TypedDict,
    Annotated,
    Literal,
    NotRequired
)
from abc import ABC, abstractmethod

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.cache.base import BaseCache
from langgraph.store.base import BaseStore
from langgraph.types import (
    Checkpointer,
    All
)
from .annotations.types import (
    Displace,
    MaybeCallable
)
from utils.stream import render_stream_events, StreamEventHandler
from schemas.model_selection import ModelSelection

class BaseAgentState(TypedDict):
    """
    Base class for agent state. All agent states should inherit from this class.
    """

    model: Displace[MaybeCallable[ModelSelection]]
    messages: Annotated[list[BaseMessage], add_messages]

class BaseGraph[State = BaseAgentState](ABC):
    """Base graph"""
    @abstractmethod
    def get_graph(self) -> StateGraph[State]:
        ...

    def get_compiled_graph(
        self,
        checkpointer: Checkpointer = None,
        *,
        cache: BaseCache | None = None,
        store: BaseStore | None = None,
        interrupt_before: All | list[str] | None = None,
        interrupt_after: All | list[str] | None = None,
        debug: bool = False,
        name: str | None = None,
    ) -> CompiledStateGraph[State]:
        return self.get_graph().compile(
            checkpointer,
            cache=cache,
            store=store,
            interrupt_before=interrupt_before,
            interrupt_after=interrupt_after,
            debug=debug,
            name=name
        )

class BaseAgent[State = BaseAgentState](BaseGraph[State]):
    """Base agent"""

    def __init__(
        self,
        checkpointer: Checkpointer = None,
        *,
        cache: BaseCache | None = None,
        store: BaseStore | None = None,
        interrupt_before: All | list[str] | None = None,
        interrupt_after: All | list[str] | None = None,
        debug: bool = False,
        name: str | None = None,
    ):
        super().__init__()
        self.checkpointer = checkpointer
        self.cache = cache
        self.store = store
        self.interrupt_before = interrupt_before
        self.interrupt_after = interrupt_after
        self.debug = debug
        self.name = name


    def get_agent(self) -> CompiledStateGraph[State]:
        return self.get_compiled_graph(
            checkpointer=self.checkpointer,
            cache=self.cache,
            store=self.store,
            interrupt_before=self.interrupt_before,
            interrupt_after=self.interrupt_after,
            debug=self.debug,
            name=self.name
        )

class BaseWorkflow[Result = Any, State = BaseAgentState](ABC):
    """
    Base class for all workflows.
    """

    def __init__(self, agent: CompiledStateGraph[State]):
        self.agent = agent

    @abstractmethod
    def _construct_initial_state(self, *args, **kwargs) -> State:
        """
        Construct the initial state for the workflow based on the provided arguments.
        """
        ...

    @abstractmethod
    def _get_result(self, state: State) -> Result:
        """
        Extract the result from the state after running the workflow.
        """
        ...

    def _run(
        self,
        *args,
        **kwargs
    ) -> State:
        """
        Define how to run the workflow.
        """
        return self.agent.invoke(self._construct_initial_state(*args, **kwargs))
    
    def invoke(
        self,
        *args,
        **kwargs
    ) -> Result:
        """
        Run the workflow and return the result.
        """
        final_state = self._run(*args, **kwargs)
        return self._get_result(final_state)
    
    async def ainvoke(
        self,
        *args,
        **kwargs
    ) -> Result:
        """
        Asynchronously run the workflow and return the result.
        """
        return self.invoke(*args, **kwargs)
    
    async def astream_events(
        self,
        *args,
        handlers: dict[str, StreamEventHandler] | None = None,
        **kwargs
    ) -> Result:
        """
        Run the workflow and stream events using the provided event handler.
        """
        state = self._construct_initial_state(*args, **kwargs)
        event_stream = self.agent.astream_events(state)
        await render_stream_events(event_stream, handlers=handlers)
        return self._get_result(state)
    
    
type InteruptType = Literal['error', 'question', 'warning', 'other']

class BaseInterupt(TypedDict):
    type: NotRequired[InteruptType]
    message: NotRequired[str | None]

__all__ = [
    "BaseAgentState",
    "BaseGraph",
    "BaseWorkflow",
    "BaseAgent",
    "InteruptType",
    "BaseInterupt"
]
