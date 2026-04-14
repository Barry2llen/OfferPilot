
import pytest
from pydantic import ValidationError

from schemas.config import Config

def test_config_validation():
    wrong_config = {
        "database": {
            "type": "sql", # should be "sqlite"
            "path": "./data/offer_pilot.db"
        }
    }

    with pytest.raises(ValidationError) as exc_info:
        Config(**wrong_config)

def test_default_config():
    config = Config()
    assert config.database.type == "sqlite"
    assert config.database.path == "./data/offer_pilot.db"

def test_config_load(sample_config):
    assert sample_config.database.type == "sqlite"
    assert sample_config.database.path == "./data/offer_pilot.db"
