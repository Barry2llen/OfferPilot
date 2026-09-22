import json

from langchain.tools import ToolRuntime, tool
from pydantic import Field

from agent.interactions import InteractionContext, ask_user
from schemas.chat_run import QueryAnswer

from ..base import (
    InputRequest,
)


class QueryRequest(InputRequest):
    question: str
    firstChoice: str
    firstChoiceDescription: str
    secondChoice: str
    secondChoiceDescription: str
    thirdChoice: str
    thirdChoiceDescription: str


@tool(response_format="content_and_artifact")
async def query(
    runtime: ToolRuntime[InteractionContext | None],
    question: str = Field(
        ..., description="The specific question to ask the user before continuing."
    ),
    firstChoice: str = Field(
        ...,
        description="The first,as well as recommended,choice to present to the user.",
    ),
    firstChoiceDescription: str = Field(
        ...,
        description="A short user-facing explanation of when to choose the recommended first choice.",
    ),
    secondChoice: str = Field(
        ..., description="The second choice to present to the user."
    ),
    secondChoiceDescription: str = Field(
        ...,
        description="A short user-facing explanation of when to choose the second choice.",
    ),
    thirdChoice: str = Field(
        ..., description="The third choice to present to the user."
    ),
    thirdChoiceDescription: str = Field(
        ...,
        description="A short user-facing explanation of when to choose the third choice.",
    ),
) -> tuple[str, dict[str, str]]:
    """
    Ask the user a specific question and present exactly three concrete options.

    Use this only when the next step depends on a user decision that cannot be
    safely inferred and the user must choose one of three options. The question
    should be concrete and user-facing. The first choice should be the
    recommended default. Every choice must include a short, user-facing
    description explaining when that option is appropriate.
    """

    ask = runtime.context.ask if runtime.context else ask_user
    resp = QueryAnswer.model_validate(
        await ask(
            QueryRequest(
                type="query",
                question=question,
                firstChoice=firstChoice,
                firstChoiceDescription=firstChoiceDescription,
                secondChoice=secondChoice,
                secondChoiceDescription=secondChoiceDescription,
                thirdChoice=thirdChoice,
                thirdChoiceDescription=thirdChoiceDescription,
            )
        )
    )

    content = {
        "choice": resp.choice,
        "note": resp.note,
    }
    artifact = {
        "question": question,
        "firstChoice": firstChoice,
        "firstChoiceDescription": firstChoiceDescription,
        "secondChoice": secondChoice,
        "secondChoiceDescription": secondChoiceDescription,
        "thirdChoice": thirdChoice,
        "thirdChoiceDescription": thirdChoiceDescription,
    }
    return json.dumps(content, ensure_ascii=False), artifact
