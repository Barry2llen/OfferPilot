from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from services.analysis_job_events import AnalysisEventHub
from utils.i18n import request_locale

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
                "Starts with a snapshot, then emits resume, job_description, progress, model_error, final and error. "
                "Events carry resource_type, resource_id, job_id and a monotonic event_id. Reconnect to replace "
                "the task projection and reload persisted records. Slow subscribers are disconnected."
            ),
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": (
                        'event: snapshot\ndata: {"event_id":1,"tasks":[{"resource_type":"resume",'
                        '"resource_id":1,"job_id":"job-1","status":"processing","progress":0.5}]}\n\n'
                    ),
                }
            },
        }
    },
)
async def stream_analysis_events(request: Request) -> StreamingResponse:
    hub: AnalysisEventHub = request.app.state.analysis_events

    async def event_stream() -> AsyncGenerator[str, None]:
        async for event in hub.stream(
            heartbeat_seconds=15, locale=request_locale(request)
        ):
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
