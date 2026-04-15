
import base64
import binascii
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

class UserInput(BaseModel):
    text: str | None = None
    image: str | None = None

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        if value is None:
            return value

        candidate = value.strip()
        if not candidate:
            raise ValueError("image must be a valid url or base64 string")

        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value

        base64_payload = candidate
        if candidate.startswith("data:"):
            header, separator, payload = candidate.partition(",")
            if not separator or ";base64" not in header:
                raise ValueError("image must be a valid url or base64 string")
            base64_payload = payload

        try:
            base64.b64decode(base64_payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image must be a valid url or base64 string") from exc

        return value
