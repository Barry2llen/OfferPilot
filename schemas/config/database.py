
from pydantic import BaseModel
from typing import Literal

class SQLiteConfig(BaseModel):
    """Configuration for SQLite database."""
    type: Literal['sqlite'] = "sqlite"
    path: str = "./data/offer_pilot.db"

class SQLConfig(BaseModel):
    """Configuration for SQL database."""
    type: Literal['sql'] = "sql"
    host: str
    port: int
    database: str
    user: str
    password: str