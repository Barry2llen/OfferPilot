
from langgraph.constants import START, END
from langgraph.graph.state import CompiledStateGraph, StateGraph

def agent2workflow[State](
    state_schema: type[State],
    agent: CompiledStateGraph[State], 
    initial_state: State,
    **kwargs
) -> CompiledStateGraph[State]:
    """
    Convert a compiled agent (StateGraph) into a workflow which is a CompiledStateGraph[State] with the given initial state.
    """

    def _set_up_initial_state_node(state: State) -> State:
        """Set up the initial state node for the workflow."""
        return initial_state
    
    workflow_graph = StateGraph[State](state_schema)
    workflow_graph.add_node("initial_state", _set_up_initial_state_node)
    workflow_graph.add_node("agent", agent)
    workflow_graph.add_edge(START, "initial_state")
    workflow_graph.add_edge("initial_state", "agent")
    workflow_graph.add_edge("agent", END)

    return workflow_graph.compile()

__all__ = [
    agent2workflow
]