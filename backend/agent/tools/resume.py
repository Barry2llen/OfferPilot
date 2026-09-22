from langchain_core.tools import tool

from ..base import InputRequest


class ListResumesRequest(InputRequest): ...


@tool(response_format="content_and_artifact")
async def list_resumes():
    pass
