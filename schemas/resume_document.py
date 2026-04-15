from datetime import datetime

from pydantic import BaseModel


class ResumeTextCreateRequest(BaseModel):
    content: str


class ResumeDocument(BaseModel):
    id: int
    file_path: str | None = None
    content: str
    upload_time: datetime
    original_filename: str | None = None
    media_type: str | None = None
