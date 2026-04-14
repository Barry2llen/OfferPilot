from contextlib import asynccontextmanager

from fastapi import FastAPI

from db.engine import configure_database_manager, dispose_database_manager
from schemas.config import load_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.database = configure_database_manager(load_config().database)
    yield
    dispose_database_manager()


app = FastAPI(lifespan=lifespan)


@app.get("/")
async def root():
    return {"message": "Hello World!"}
