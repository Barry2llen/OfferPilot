import pytest
from pydantic import ValidationError

from agent.input.user_input import UserInput


def test_user_input_accepts_http_url() -> None:
    payload = UserInput(image="https://example.com/demo.png")

    assert payload.image == "https://example.com/demo.png"


def test_user_input_accepts_data_url_base64() -> None:
    payload = UserInput(image="data:image/png;base64,aGVsbG8=")

    assert payload.image == "data:image/png;base64,aGVsbG8="


def test_user_input_accepts_raw_base64() -> None:
    payload = UserInput(image="aGVsbG8=")

    assert payload.image == "aGVsbG8="


def test_user_input_rejects_invalid_image_value() -> None:
    with pytest.raises(ValidationError):
        UserInput(image="not-a-url-or-base64")
