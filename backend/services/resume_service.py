from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from db.models import ResumeDocumentORM
from db.repositories import ResumeDocumentRepository
from exceptions import (
    EmptyResumeContentError,
    ResumeFileNotFoundError,
    ResumeNotFoundError,
    ResumeValidationError,
    UnsupportedResumeFileError,
)
from schemas.resume_document import ResumeDetail, ResumeListItem


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
    ) -> None:
        self._repository = repository
        self._upload_dir = Path(upload_dir)

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
        return ResumeDetail(
            id=document.id,
            file_path=document.file_path,
            upload_time=document.upload_time,
            original_filename=document.original_filename,
            media_type=document.media_type,
            has_file=has_file,
            preview_url=self._build_preview_url(document.id) if has_file else None,
        )

    def _to_list_item(self, document: ResumeDocumentORM) -> ResumeListItem:
        has_file = document.file_path is not None
        return ResumeListItem(
            id=document.id,
            file_path=document.file_path,
            upload_time=document.upload_time,
            original_filename=document.original_filename,
            media_type=document.media_type,
            has_file=has_file,
            preview_url=self._build_preview_url(document.id) if has_file else None,
        )

    def _require_resume(self, resume_id: int) -> ResumeDocumentORM:
        document = self._repository.get_by_id(resume_id)
        if document is None:
            raise ResumeNotFoundError(f"Resume not found: {resume_id}")
        return document

    def _build_preview_url(self, resume_id: int) -> str:
        return f"/resumes/{resume_id}/file"

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
