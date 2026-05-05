from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from db.models import ResumeDocumentORM, ResumeExtractionORM
from db.repositories import ResumeDocumentRepository, ResumeExtractionRepository
from exceptions import (
    EmptyResumeContentError,
    ResumeFileNotFoundError,
    ResumeNotFoundError,
    ResumeValidationError,
    UnsupportedResumeFileError,
)
from schemas.resume_document import ResumeDetail, ResumeListItem
from schemas.resume import Resume


@dataclass(slots=True)
class UploadedResumeFile:
    filename: str
    content_type: str | None
    content: bytes


@dataclass(slots=True)
class StoredResumeFile:
    path: Path
    media_type: str | None
    filename: str | None


class ResumeService:
    """Service for creating and managing uploaded resume files."""

    def __init__(
        self,
        repository: ResumeDocumentRepository,
        upload_dir: str | Path,
        extraction_repository: ResumeExtractionRepository | None = None,
    ) -> None:
        self._repository = repository
        self._upload_dir = Path(upload_dir)
        self._extraction_repository = extraction_repository

    def list_resumes(self) -> list[ResumeListItem]:
        return [self._to_list_item(document) for document in self._repository.list_all()]

    def get_resume(self, resume_id: int) -> ResumeDetail:
        return self._to_detail(self._require_resume(resume_id))

    def create_from_file(self, uploaded_file: UploadedResumeFile) -> ResumeDetail:
        filename = Path(uploaded_file.filename).name
        if not filename:
            raise ResumeValidationError("Uploaded file name is required.")
        if not uploaded_file.content:
            raise EmptyResumeContentError("Uploaded file is empty.")

        suffix = Path(filename).suffix.lower()
        self._validate_suffix(suffix)

        saved_path = self._build_target_path(suffix)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_bytes(uploaded_file.content)

        try:
            created = self._repository.create(
                ResumeDocumentORM(
                    file_path=self._to_storage_path(saved_path),
                    original_filename=filename,
                    media_type=uploaded_file.content_type,
                )
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            saved_path.unlink(missing_ok=True)
            raise

        return self._to_detail(created)

    def replace_resume_file(
        self,
        resume_id: int,
        uploaded_file: UploadedResumeFile,
    ) -> ResumeDetail:
        document = self._require_resume(resume_id)
        previous_file_path = document.file_path
        previous_resolved_path: Path | None = None
        if previous_file_path is not None:
            previous_resolved_path = self._resolve_storage_path(
                previous_file_path,
                require_exists=False,
            )

        filename = Path(uploaded_file.filename).name
        if not filename:
            raise ResumeValidationError("Uploaded file name is required.")
        if not uploaded_file.content:
            raise EmptyResumeContentError("Uploaded file is empty.")

        suffix = Path(filename).suffix.lower()
        self._validate_suffix(suffix)

        saved_path = self._build_target_path(suffix)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_bytes(uploaded_file.content)

        try:
            document.file_path = self._to_storage_path(saved_path)
            document.original_filename = filename
            document.media_type = uploaded_file.content_type
            updated = self._repository.update(document)
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            saved_path.unlink(missing_ok=True)
            raise

        if previous_resolved_path is not None and previous_resolved_path != saved_path.resolve():
            self._delete_file_quietly(previous_resolved_path)

        return self._to_detail(updated)

    def delete_resume(self, resume_id: int) -> None:
        document = self._require_resume(resume_id)
        file_path = document.file_path

        try:
            if self._extraction_repository is not None:
                self._extraction_repository.delete_by_resume_id(resume_id)
            deleted = self._repository.delete(resume_id)
            if not deleted:
                raise ResumeNotFoundError(f"Resume not found: {resume_id}")
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

        if file_path is not None:
            self._delete_file_quietly(
                self._resolve_storage_path(file_path, require_exists=False)
            )

    def get_resume_file(self, resume_id: int) -> StoredResumeFile:
        document = self._require_resume(resume_id)
        if document.file_path is None:
            raise ResumeFileNotFoundError(f"Resume file not found: {resume_id}")

        return StoredResumeFile(
            path=self._resolve_storage_path(document.file_path),
            media_type=document.media_type,
            filename=document.original_filename,
        )

    def begin_extraction(self, resume_id: int, selection_id: int) -> ResumeDetail:
        self._require_extraction_repository()
        document = self._require_resume(resume_id)
        extraction = ResumeExtractionORM(
            resume_id=resume_id,
            status="processing",
            raw_text=None,
            sections=[],
            summary=None,
            error_message=None,
            model_selection_id=selection_id,
            completed_at=None,
        )

        try:
            self._extraction_repository.upsert(extraction)
            self._extraction_repository.commit()
        except Exception:
            self._extraction_repository.rollback()
            raise

        return self._to_detail(document)

    def complete_extraction(
        self,
        resume_id: int,
        selection_id: int,
        resume: Resume,
    ) -> ResumeDetail:
        self._require_extraction_repository()
        document = self._require_resume(resume_id)
        sections = [
            section.model_dump(mode="json")
            for section in resume.sections
        ]
        extraction = ResumeExtractionORM(
            resume_id=resume_id,
            status="parsed",
            raw_text=resume.raw_text,
            sections=sections,
            summary=self._build_summary(resume.raw_text),
            error_message=None,
            model_selection_id=selection_id,
            completed_at=datetime.now(),
        )

        try:
            self._extraction_repository.upsert(extraction)
            self._extraction_repository.commit()
        except Exception:
            self._extraction_repository.rollback()
            raise

        return self._to_detail(document)

    def fail_extraction(
        self,
        resume_id: int,
        selection_id: int,
        error_message: str,
    ) -> ResumeDetail:
        self._require_extraction_repository()
        document = self._require_resume(resume_id)
        extraction = ResumeExtractionORM(
            resume_id=resume_id,
            status="failed",
            raw_text=None,
            sections=[],
            summary=None,
            error_message=error_message,
            model_selection_id=selection_id,
            completed_at=datetime.now(),
        )

        try:
            self._extraction_repository.upsert(extraction)
            self._extraction_repository.commit()
        except Exception:
            self._extraction_repository.rollback()
            raise

        return self._to_detail(document)

    def _build_target_path(self, suffix: str) -> Path:
        return self._upload_dir / f"{uuid4().hex}{suffix}"

    def _validate_suffix(self, suffix: str) -> None:
        if suffix == ".doc":
            raise UnsupportedResumeFileError("Legacy .doc files are not supported.")

        if suffix not in {".pdf", ".docx", ".png", ".jpg", ".jpeg"}:
            raise UnsupportedResumeFileError(
                f"Unsupported resume file type: {suffix or '<missing>'}"
            )

    def _to_storage_path(self, file_path: Path) -> str:
        resolved_path = file_path.resolve()
        try:
            return resolved_path.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return resolved_path.as_posix()

    def _to_detail(self, document: ResumeDocumentORM) -> ResumeDetail:
        has_file = document.file_path is not None
        extraction = self._get_extraction(document.id)
        parse_payload = self._build_parse_payload(extraction, include_details=True)
        return ResumeDetail(
            id=document.id,
            file_path=document.file_path,
            upload_time=document.upload_time,
            original_filename=document.original_filename,
            media_type=document.media_type,
            has_file=has_file,
            preview_url=self._build_preview_url(document.id) if has_file else None,
            **parse_payload,
        )

    def _to_list_item(self, document: ResumeDocumentORM) -> ResumeListItem:
        has_file = document.file_path is not None
        extraction = self._get_extraction(document.id)
        parse_payload = self._build_parse_payload(extraction, include_details=False)
        return ResumeListItem(
            id=document.id,
            file_path=document.file_path,
            upload_time=document.upload_time,
            original_filename=document.original_filename,
            media_type=document.media_type,
            has_file=has_file,
            preview_url=self._build_preview_url(document.id) if has_file else None,
            **parse_payload,
        )

    def _require_resume(self, resume_id: int) -> ResumeDocumentORM:
        document = self._repository.get_by_id(resume_id)
        if document is None:
            raise ResumeNotFoundError(f"Resume not found: {resume_id}")
        return document

    def _build_preview_url(self, resume_id: int) -> str:
        return f"/resumes/{resume_id}/file"

    def _get_extraction(self, resume_id: int) -> ResumeExtractionORM | None:
        if self._extraction_repository is None:
            return None
        return self._extraction_repository.get_by_resume_id(resume_id)

    def _build_parse_payload(
        self,
        extraction: ResumeExtractionORM | None,
        *,
        include_details: bool,
    ) -> dict[str, Any]:
        if extraction is None:
            payload: dict[str, Any] = {
                "parse_status": "unparsed",
                "parse_error": None,
                "parsed_at": None,
                "summary": None,
                "section_count": 0,
                "fact_count": 0,
            }
            if include_details:
                payload.update({"raw_text": "", "sections": []})
            return payload

        sections = extraction.sections if isinstance(extraction.sections, list) else []
        payload = {
            "parse_status": extraction.status,
            "parse_error": extraction.error_message,
            "parsed_at": extraction.completed_at,
            "summary": extraction.summary,
            "section_count": len(sections),
            "fact_count": self._count_facts(sections),
        }
        if include_details:
            payload.update(
                {
                    "raw_text": extraction.raw_text or "",
                    "sections": sections,
                }
            )
        return payload

    def _count_facts(self, sections: list[Any]) -> int:
        count = 0
        for section in sections:
            if isinstance(section, dict) and isinstance(section.get("facts"), list):
                count += len(section["facts"])
        return count

    def _build_summary(self, raw_text: str) -> str | None:
        normalized = " ".join(raw_text.split())
        if not normalized:
            return None
        return normalized[:180]

    def _require_extraction_repository(self) -> None:
        if self._extraction_repository is None:
            raise RuntimeError("Resume extraction repository is required.")

    def _resolve_storage_path(
        self,
        file_path: str,
        *,
        require_exists: bool = True,
    ) -> Path:
        candidate = Path(file_path)
        resolved = candidate.resolve() if candidate.is_absolute() else (Path.cwd() / candidate).resolve()
        allowed_roots = (Path.cwd().resolve(), self._upload_dir.resolve())
        if not any(self._is_relative_to(resolved, root) for root in allowed_roots):
            raise ResumeFileNotFoundError("Resume file not found.")
        if require_exists and not resolved.is_file():
            raise ResumeFileNotFoundError("Resume file not found.")
        return resolved

    def _is_relative_to(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    def _delete_file_quietly(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return
