from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from api import resume_router
from db.engine import configure_database_manager, dispose_database_manager
from schemas.config import Config, load_config


class RootMessageResponse(BaseModel):
    message: str = Field(
        description="服务探活响应信息。",
        examples=["Hello World!"],
    )


def create_app(config: Config | None = None) -> FastAPI:
    target_config = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = target_config
        app.state.database = configure_database_manager(target_config.database)
        app.state.database.initialize_tables()
        yield
        dispose_database_manager()

    app = FastAPI(
        title="OfferPilot API",
        description=(
            "OfferPilot 提供简历文件管理与在线预览接口。"
            "Swagger 文档可用于查看接口用途、参数要求、错误场景和响应示例。"
        ),
        version="0.1.0",
        openapi_tags=[
            {
                "name": "resumes",
                "description": "简历文件管理接口，包含上传、替换、查询、预览和删除。",
            }
        ],
        lifespan=lifespan,
    )
    app.include_router(resume_router)

    @app.get(
        "/",
        response_model=RootMessageResponse,
        summary="服务探活",
        description="返回一个简单的服务可用性响应，用于确认 API 服务已成功启动。",
        response_description="返回固定的探活消息。",
    )
    async def root() -> RootMessageResponse:
        return {"message": "Hello World!"}

    return app


app = create_app()
