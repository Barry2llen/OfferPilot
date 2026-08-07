from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agent.agents.supervisor import SupervisorAgent, get_supervisor_tools
from agent.checkpointers import DatabaseCheckpointer
from agent.compaction import DatabaseCompactionModelResolver
from api import ai_router, job_description_router, model_config_router, resume_router
from db.engine import (
    configure_async_database_manager,
    configure_database_manager,
    dispose_async_database_manager,
    dispose_database_manager,
)
from schemas.config import Config, load_config
from services.jd_analysis_jobs import JdAnalysisJobManager
from services.resume_extraction_jobs import ResumeExtractionJobManager
from utils.asyncio_windows import install_windows_connection_reset_filter
from utils.frontend_static import mount_frontend
from utils.i18n import (
    localize_error,
    localize_validation_message,
    request_locale,
    resolve_locale,
)


class HealthResponse(BaseModel):
    message: str = Field(
        description="Health check response message.",
        examples=["Hello World!"],
    )


def create_app(
    config: Config | None = None,
    frontend_dist: Path | str | None = None,
) -> FastAPI:
    target_config = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        install_windows_connection_reset_filter()
        app.state.config = target_config
        app.state.database = configure_database_manager(target_config.database)
        app.state.async_database = configure_async_database_manager(
            target_config.database
        )
        app.state.database.initialize_tables()
        app.state.resume_extraction_jobs = ResumeExtractionJobManager(
            config=target_config,
            database=app.state.database,
        )
        app.state.jd_analysis_jobs = JdAnalysisJobManager(
            config=target_config,
            database=app.state.database,
        )
        app.state.checkpointer = DatabaseCheckpointer(
            app.state.database,
            app.state.async_database,
        )
        app.state.supervisor_agent = SupervisorAgent(
            checkpointer=app.state.checkpointer,
            config=target_config,
            tools=await get_supervisor_tools(config=target_config),
            compaction_model_resolver=DatabaseCompactionModelResolver(
                app.state.database
            ),
        ).get_agent()
        yield
        await app.state.resume_extraction_jobs.shutdown()
        await app.state.jd_analysis_jobs.shutdown()
        await dispose_async_database_manager()
        dispose_database_manager()

    app = FastAPI(
        title="OfferPilot API",
        description=(
            "OfferPilot provides resume file management, model configuration, and AI chat APIs. "
            "Use the Swagger documentation to review operations, parameters, errors, and response examples."
        ),
        version="0.1.0",
        openapi_tags=[
            {
                "name": "resumes",
                "description": "Resume file management, including upload, parsing, replacement, retrieval, preview, and deletion.",
            },
            {
                "name": "job-descriptions",
                "description": "Job description analysis from text, URLs, and images, with historical result management.",
            },
            {
                "name": "model-config",
                "description": "Model provider, model selection, and Supervisor context compaction configuration for available AI services.",
            },
            {
                "name": "ai",
                "description": "AI chat operations using SupervisorAgent and database checkpoints for conversation state.",
            },
        ],
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def add_locale_headers(request: Request, call_next):
        request.state.locale = resolve_locale(request.headers.get("Accept-Language"))
        response = await call_next(request)
        response.headers["Content-Language"] = request_locale(request)
        return response

    @app.exception_handler(HTTPException)
    async def localized_http_exception(
        request: Request, error: HTTPException
    ) -> JSONResponse:
        detail = error.detail
        if isinstance(detail, str):
            detail = localize_error(detail, request_locale(request))
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": detail},
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def localized_validation_exception(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        locale = request_locale(request)
        details = []
        for item in error.errors():
            details.append(
                {
                    "type": item.get("type", "value_error"),
                    "loc": list(item.get("loc", ())),
                    "msg": localize_validation_message(
                        str(item.get("msg", "")), locale
                    ),
                }
            )
        return JSONResponse(status_code=422, content={"detail": details})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=target_config.cors.allow_origins,
        allow_credentials=target_config.cors.allow_credentials,
        allow_methods=target_config.cors.allow_methods,
        allow_headers=target_config.cors.allow_headers,
    )
    app.include_router(resume_router)
    app.include_router(job_description_router)
    app.include_router(model_config_router)
    app.include_router(ai_router)

    @app.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="Return a simple response confirming that the API service has started successfully.",
        response_description="Returns the fixed health check message.",
    )
    async def health() -> HealthResponse:
        return HealthResponse(message="Hello World!")

    mount_frontend(app, frontend_dist)

    return app


app = create_app()
