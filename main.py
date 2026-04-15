from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import resume_router
from db.engine import configure_database_manager, dispose_database_manager
from schemas.config import Config, load_config


def create_app(config: Config | None = None) -> FastAPI:
    target_config = config or load_config()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.config = target_config
        app.state.database = configure_database_manager(target_config.database)
        app.state.database.initialize_tables()
        yield
        dispose_database_manager()

    app = FastAPI(lifespan=lifespan)
    app.include_router(resume_router)

    @app.get("/")
    async def root():
        return {"message": "Hello World!"}

    return app


app = create_app()
