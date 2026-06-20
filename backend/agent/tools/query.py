
import json
from typing import (
    TypedDict,
    NotRequired,
    Literal
)
from pydantic import Field
from langgraph.types import interrupt
from langchain.tools import tool

from ..base import (
    BaseInterupt,
)

class QueryInterupt(BaseInterupt):
    question: str
    firstChoice: str
    firstChoiceDescription: str
    secondChoice: str
    secondChoiceDescription: str
    thirdChoice: str
    thirdChoiceDescription: str

type AnswerType = Literal['firstChoice', 'secondChoice', 'thirdChoice', 'other']

class Answer(TypedDict):
    choice: AnswerType
    note: NotRequired[str | None]

@tool(response_format="content_and_artifact", extras={"interupt": True})
async def query(
    question: str = Field(..., description="The specific question to ask the user before continuing."),
    firstChoice: str = Field(..., description="The first,as well as recommended,choice to present to the user."),
    firstChoiceDescription: str = Field(..., description="A short user-facing explanation of when to choose the recommended first choice."),
    secondChoice: str = Field(..., description="The second choice to present to the user."),
    secondChoiceDescription: str = Field(..., description="A short user-facing explanation of when to choose the second choice."),
    thirdChoice: str = Field(..., description="The third choice to present to the user."),
    thirdChoiceDescription: str = Field(..., description="A short user-facing explanation of when to choose the third choice."),
) -> tuple[str, dict[str, str]]:
    """
    Ask the user a specific question and present exactly three concrete options.

    Use this only when the next step depends on a user decision that cannot be
    safely inferred and the user must choose one of three options. The question
    should be concrete and user-facing. The first choice should be the
    recommended default. Every choice must include a short, user-facing
    description explaining when that option is appropriate.
    """

    resp: Answer = interrupt(
        QueryInterupt(
            type='query',
            question=question,
            firstChoice=firstChoice,
            firstChoiceDescription=firstChoiceDescription,
            secondChoice=secondChoice,
            secondChoiceDescription=secondChoiceDescription,
            thirdChoice=thirdChoice,
            thirdChoiceDescription=thirdChoiceDescription,
        )
    )

    content = {
        "choice": resp["choice"],
        "note": resp.get("note", None),
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
