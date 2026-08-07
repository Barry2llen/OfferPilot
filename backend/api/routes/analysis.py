from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from services.analysis_job_events import AnalysisEventHub

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.get(
    "/events",
    summary="Stream analysis task events",
    description=(
        "Stream resume and job description analysis lifecycle events. The connection is independent "
        "of the request that created the task, so pages can continue to observe background work."
    ),
    response_description="Returns a text/event-stream response.",
    responses={
        200: {
            "description": (
                "Returns resume, job_description, progress, model_error, final, and error events."
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": (
                        'event: progress\ndata: {"resume_id":1,"progress":0.5,'
                        '"message":"正在解析简历"}\n\n'
                    ),
                }
            },
        }
    },
)
async def stream_analysis_events(request: Request) -> StreamingResponse:
    hub: AnalysisEventHub = request.app.state.analysis_events

    async def event_stream() -> AsyncGenerator[str, None]:
        async for event in hub.stream(heartbeat_seconds=15):
            yield event

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
