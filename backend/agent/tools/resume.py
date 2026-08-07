from langchain_core.tools import tool

from ..base import BaseInterupt


class ListResumesInterupt(BaseInterupt): ...


@tool(response_format="content_and_artifact")
async def list_resumes():
    pass
