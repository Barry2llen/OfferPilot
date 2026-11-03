import json
from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from agent.interactions import InteractionContext, ask_user
from schemas.query import QueryAnswer, QueryOption, QueryRequest, QuerySelectionMode


@tool(response_format="content_and_artifact")
async def query(
    runtime: ToolRuntime[InteractionContext | None],
    question: str = Field(
        ...,
        min_length=1,
        description="The specific question to ask the user before continuing.",
    ),
    selection_mode: QuerySelectionMode = Field(
        ...,
        description="Explicitly choose single or multiple selection for this question.",
    ),
    options: list[QueryOption] = Field(
        ...,
        min_length=2,
        description="At least two concrete options with unique IDs, labels and descriptions. The first is recommended; there is no fixed upper limit.",
    ),
) -> tuple[str, dict[str, Any]]:
    """Ask a user decision with a dynamic list of options and single/multiple mode.

    Use only when the next step depends on a decision that cannot be inferred.
    Provide at least two options, each with a unique ID, label, and short
    explanation. Put the recommended option first. Explicitly choose single
    for mutually exclusive alternatives or multiple for compatible decisions.
    Users may instead enter a free-text answer and may add a separate note;
    multiple mode also allows combining selections and free text.
    """
    request = QueryRequest(
        question=question, selection_mode=selection_mode, options=options
    )
    ask = runtime.context.ask if runtime.context else ask_user
    response = QueryAnswer.model_validate(await ask(request.model_dump())).for_request(
        request
    )
    selected = set(response.selected_option_ids)
    content = {
        "selected_options": [
            {"id": option.id, "label": option.label}
            for option in request.options
            if option.id in selected
        ],
        "free_text": response.free_text,
        "note": response.note,
    }
    return (
        json.dumps(content, ensure_ascii=False),
        request.model_dump(exclude={"type"}),
    )
