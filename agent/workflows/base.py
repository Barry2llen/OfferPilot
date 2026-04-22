from typing import Any
from abc import ABC, abstractmethod

from langgraph.graph.state import CompiledStateGraph

from utils.stream import render_stream_events, StreamEventHandler
from ..state import BaseAgentState

class BaseWorkflow[Result = Any, State = BaseAgentState](ABC):
    """
    Base class for all workflows. All workflows should inherit from this class and implement the `run` method.
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