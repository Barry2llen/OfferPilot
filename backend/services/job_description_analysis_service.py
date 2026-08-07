import base64
from datetime import datetime
from pathlib import Path
from typing import Any

from db.models import ChatFileORM, JobDescriptionAnalysisORM
from db.repositories import JobDescriptionAnalysisRepository
from exceptions import (
    ChatFileNotFoundError,
    JobDescriptionAnalysisNotFoundError,
    JobDescriptionAnalysisValidationError,
    UnsupportedChatFileError,
)
from schemas.chat_file import StoredChatFile
from schemas.job_description import JobDescription
from schemas.job_description_analysis import (
    JobDescriptionAnalysisDetail,
    JobDescriptionAnalysisListItem,
)

_IMAGE_SUFFIX_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class JobDescriptionAnalysisService:
    """Service for creating and persisting JD analysis results."""

    def __init__(
        self,
        repository: JobDescriptionAnalysisRepository,
    ) -> None:
        self._repository = repository

    def list_analyses(self) -> list[JobDescriptionAnalysisListItem]:
        return [self._to_list_item(record) for record in self._repository.list_all()]

    def get_analysis(self, analysis_id: int) -> JobDescriptionAnalysisDetail:
        return self._to_detail(self._require_analysis(analysis_id))

    def create_processing(
        self,
        *,
        selection_id: int,
        source_url: str | None,
        image_file_ids: list[str],
    ) -> JobDescriptionAnalysisDetail:
        record = JobDescriptionAnalysisORM(
            status="processing",
            source_url=source_url.strip()
            if source_url and source_url.strip()
            else None,
            source_image_file_ids=image_file_ids,
            result={},
            model_selection_id=selection_id,
        )
        try:
            created = self._repository.create(record)
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return self._to_detail(created)

    def complete_analysis(
        self,
        analysis_id: int,
        selection_id: int,
        job_description: JobDescription,
    ) -> JobDescriptionAnalysisDetail:
        record = self._require_analysis(analysis_id)
        blocks = job_description.blocks
        record.status = "parsed"
        record.raw_text = job_description.raw_text
        record.result = job_description.model_dump(mode="json")
        record.summary = self._build_summary(job_description.raw_text)
        record.error_message = None
        record.model_selection_id = selection_id
        record.job_title = job_description.job_title or None
        record.company_name = job_description.company_name
        record.primary_location = job_description.primary_location
        record.block_count = len(blocks)
        record.fact_count = sum(len(block.facts) for block in blocks)
        record.completed_at = datetime.now()

        try:
            updated = self._repository.update(record)
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return self._to_detail(updated)

    def fail_analysis(
        self,
        analysis_id: int,
        selection_id: int,
        error_message: str,
    ) -> JobDescriptionAnalysisDetail:
        record = self._require_analysis(analysis_id)
        record.status = "failed"
        record.error_message = error_message
        record.model_selection_id = selection_id
        record.completed_at = datetime.now()

        try:
            updated = self._repository.update(record)
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return self._to_detail(updated)

    def delete_analysis(self, analysis_id: int) -> None:
        try:
            deleted = self._repository.delete(analysis_id)
            if not deleted:
                raise JobDescriptionAnalysisNotFoundError(
                    f"Job description analysis not found: {analysis_id}"
                )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

    def validate_sources(
        self,
        *,
        jd_text: str | None,
        source_url: str | None,
        image_file_ids: list[str],
    ) -> None:
        if jd_text and jd_text.strip():
            return
        if source_url and source_url.strip():
            return
        if image_file_ids:
            return
        raise JobDescriptionAnalysisValidationError(
            "JD text, source URL, or at least one image is required."
        )

    def image_record_to_data_url(self, record: ChatFileORM) -> str:
        suffix = Path(record.original_filename).suffix.lower()
        mime_type = record.media_type or _IMAGE_SUFFIX_MIME_TYPES.get(suffix)
        if suffix not in _IMAGE_SUFFIX_MIME_TYPES or mime_type not in set(
            _IMAGE_SUFFIX_MIME_TYPES.values()
        ):
            raise UnsupportedChatFileError(
                f"Unsupported JD image file type: {suffix or '<missing>'}"
            )

        path = self._resolve_path(record.storage_path)
        return self._path_to_data_url(path, _IMAGE_SUFFIX_MIME_TYPES[suffix])

    def stored_file_to_data_url(self, stored: StoredChatFile) -> str:
        suffix = Path(stored.filename).suffix.lower()
        mime_type = stored.media_type or _IMAGE_SUFFIX_MIME_TYPES.get(suffix)
        if suffix not in _IMAGE_SUFFIX_MIME_TYPES or mime_type not in set(
            _IMAGE_SUFFIX_MIME_TYPES.values()
        ):
            raise UnsupportedChatFileError(
                f"Unsupported JD image file type: {suffix or '<missing>'}"
            )
        return self._path_to_data_url(
            Path(stored.path), _IMAGE_SUFFIX_MIME_TYPES[suffix]
        )

    def _require_analysis(self, analysis_id: int) -> JobDescriptionAnalysisORM:
        record = self._repository.get_by_id(analysis_id)
        if record is None:
            raise JobDescriptionAnalysisNotFoundError(
                f"Job description analysis not found: {analysis_id}"
            )
        return record

    def _to_list_item(
        self, record: JobDescriptionAnalysisORM
    ) -> JobDescriptionAnalysisListItem:
        return JobDescriptionAnalysisListItem(
            id=record.id,
            status=record.status,
            source_url=record.source_url,
            source_image_file_ids=self._string_list(record.source_image_file_ids),
            summary=record.summary,
            error_message=record.error_message,
            model_selection_id=record.model_selection_id,
            job_title=record.job_title,
            company_name=record.company_name,
            primary_location=record.primary_location,
            block_count=record.block_count,
            fact_count=record.fact_count,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )

    def _to_detail(
        self, record: JobDescriptionAnalysisORM
    ) -> JobDescriptionAnalysisDetail:
        result = self._parse_result(record.result)
        return JobDescriptionAnalysisDetail(
            **self._to_list_item(record).model_dump(),
            raw_text=record.raw_text or "",
            result=result,
        )

    def _parse_result(self, value: Any) -> JobDescription | None:
        if not isinstance(value, dict) or not value:
            return None
        return JobDescription.model_validate(value)

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    def _build_summary(self, raw_text: str) -> str | None:
        normalized = " ".join(raw_text.split())
        if not normalized:
            return None
        return normalized[:180]

    def _resolve_path(self, storage_path: str) -> Path:
        candidate = Path(storage_path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (Path.cwd() / candidate).resolve()
        )
        if not resolved.is_file():
            raise ChatFileNotFoundError("Chat file not found.")
        return resolved

    def _path_to_data_url(self, path: Path, mime_type: str) -> str:
        payload = path.read_bytes()
        if not payload:
            raise JobDescriptionAnalysisValidationError("JD image file is empty.")
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"
