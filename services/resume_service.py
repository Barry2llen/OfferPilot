from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from db.models import ResumeDocumentORM
from db.repositories import ResumeDocumentRepository
from schemas.resume_document import ResumeDocument
from services.document_parser_service import (
    DocumentParserService,
    UnsupportedResumeFileError,
)


class EmptyResumeContentError(ValueError):
    """Raised when the provided resume content is blank."""


@dataclass(slots=True)
class UploadedResumeFile:
    filename: str
    content_type: str | None
    content: bytes


class ResumeService:
    """Service for creating resume records from text or uploaded files."""

    def __init__(
        self,
        repository: ResumeDocumentRepository,
        parser: DocumentParserService,
        upload_dir: str | Path,
    ) -> None:
        self._repository = repository
        self._parser = parser
        self._upload_dir = Path(upload_dir)

    def create_from_text(self, content: str) -> ResumeDocument:
        normalized_content = self._normalize_content(content)
        try:
            created = self._repository.create(
                ResumeDocumentORM(
                    file_path=None,
                    content=normalized_content,
                    original_filename=None,
                    media_type=None,
                )
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise

        return self._to_schema(created)

    def create_from_file(self, uploaded_file: UploadedResumeFile) -> ResumeDocument:
        filename = Path(uploaded_file.filename).name
        if not filename:
            raise ValueError("Uploaded file name is required.")
        if not uploaded_file.content:
            raise EmptyResumeContentError("Uploaded file is empty.")

        suffix = Path(filename).suffix.lower()
        self._validate_suffix(suffix)

        saved_path = self._build_target_path(suffix)
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_bytes(uploaded_file.content)

        try:
            extracted_content = self._normalize_content(
                self._parser.extract_text(saved_path)
            )
            created = self._repository.create(
                ResumeDocumentORM(
                    file_path=self._to_storage_path(saved_path),
                    content=extracted_content,
                    original_filename=filename,
                    media_type=uploaded_file.content_type,
                )
            )
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            saved_path.unlink(missing_ok=True)
            raise

        return self._to_schema(created)

    def _build_target_path(self, suffix: str) -> Path:
        return self._upload_dir / f"{uuid4().hex}{suffix}"

    def _normalize_content(self, content: str) -> str:
        normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise EmptyResumeContentError("Resume content is empty.")
        return normalized

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

    def _to_schema(self, document: ResumeDocumentORM) -> ResumeDocument:
        return ResumeDocument(
            id=document.id,
            file_path=document.file_path,
            content=document.content,
            upload_time=document.upload_time,
            original_filename=document.original_filename,
            media_type=document.media_type,
        )
