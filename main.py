from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.agents.supervisor import SupervisorAgent
from agent.checkpointers import DatabaseCheckpointer
from agent.tools import get_all_tools
from api import ai_router, model_config_router, resume_router
from db.engine import (
    configure_async_database_manager,
    configure_database_manager,
    dispose_async_database_manager,
    dispose_database_manager,
)
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
        app.state.async_database = configure_async_database_manager(target_config.database)
        app.state.database.initialize_tables()
        app.state.checkpointer = DatabaseCheckpointer(
            app.state.database,
            app.state.async_database,
        )
        app.state.supervisor_agent = SupervisorAgent(
            checkpointer=app.state.checkpointer,
            config=target_config,
            tools=get_all_tools(target_config, allow_mcp_fallback=True),
        ).get_agent()
        yield
        await dispose_async_database_manager()
        dispose_database_manager()

    app = FastAPI(
        title="OfferPilot API",
        description=(
            "OfferPilot 提供简历文件管理、模型配置管理与基础 AI 对话接口。"
            "Swagger 文档可用于查看接口用途、参数要求、错误场景和响应示例。"
        ),
        version="0.1.0",
        openapi_tags=[
            {
                "name": "resumes",
                "description": "简历文件管理接口，包含上传、替换、查询、预览和删除。",
            },
            {
                "name": "model-config",
                "description": "模型供应商与模型选择配置接口，用于维护 AI 服务可用模型。",
            },
            {
                "name": "ai",
                "description": "基础 AI 对话接口，使用 SupervisorAgent 与数据库检查点保存会话状态。",
            }
        ],
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=target_config.cors.allow_origins,
        allow_credentials=target_config.cors.allow_credentials,
        allow_methods=target_config.cors.allow_methods,
        allow_headers=target_config.cors.allow_headers,
    )
    app.include_router(resume_router)
    app.include_router(model_config_router)
    app.include_router(ai_router)

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
