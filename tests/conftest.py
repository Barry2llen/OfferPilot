import pytest

from schemas.config import Config

@pytest.fixture
def sample_config() -> Config:
    from ruamel.yaml import YAML
    
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with open('config.example.yaml', 'r', encoding='utf-8') as f:
      config = yaml.load(f)
    return Config(**config)