from datetime import datetime

from pydantic import BaseModel


class ResumeDetail(BaseModel):
    id: int
    file_path: str | None = None
    content: str
    upload_time: datetime
    original_filename: str | None = None
    media_type: str | None = None
    has_file: bool
    preview_url: str | None = None


class ResumeDocument(ResumeDetail):
    pass


class ResumeListItem(BaseModel):
    id: int
    file_path: str | None = None
    upload_time: datetime
    original_filename: str | None = None
    media_type: str | None = None
    content_preview: str
    has_file: bool
    preview_url: str | None = None
