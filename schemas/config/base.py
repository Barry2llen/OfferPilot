
from functools import lru_cache

from pydantic import BaseModel

from .database import (
    SQLiteConfig,
    SQLConfig
)
from utils.logger import logger

class Config(BaseModel):

    """Configuration for the application, including model providers and other settings."""

    database: SQLiteConfig | SQLConfig = SQLiteConfig()

@lru_cache(maxsize=1)
def load_config() -> Config:
    """Load the configuration from a file or environment variables."""
    from path import Path
    from ruamel.yaml import YAML
    yaml = YAML().indent(mapping=2, sequence=4, offset=2)

    config_path = Path('config.yaml')
    if not config_path.exists():
        return Config()
    
    with config_path.open() as f:
        config_data = yaml.load(f)
    
    try:
        return Config(**config_data)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return Config()