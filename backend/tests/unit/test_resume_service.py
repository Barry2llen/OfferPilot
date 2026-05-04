from pathlib import Path

import pytest
from sqlalchemy import text

from db.engine import DatabaseManager
from db.repositories import ResumeDocumentRepository
from exceptions import EmptyResumeContentError, UnsupportedResumeFileError
from services.resume_service import ResumeService, UploadedResumeFile


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def _resolve_saved_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else Path.cwd() / path


def test_create_resume_from_file_persists_metadata(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )

        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.png",
                content_type="image/png",
                content=b"image-bytes",
            )
        )
        stored = session.execute(
            text(
                "SELECT file_path, original_filename, media_type "
                "FROM tb_resume WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert created.original_filename == "resume.png"
    assert created.media_type == "image/png"
    assert created.has_file is True
    assert created.preview_url == f"/resumes/{created.id}/file"
    assert stored[1:] == ("resume.png", "image/png")
    assert stored[0] is not None
    assert _resolve_saved_path(stored[0]).exists()


def test_list_resumes_returns_summary_in_descending_order(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )
        first = service.create_from_file(
            UploadedResumeFile(
                filename="resume.png",
                content_type="image/png",
                content=b"image-bytes",
            )
        )
        second = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )

        listed = service.list_resumes()

    assert [item.id for item in listed] == [second.id, first.id]
    assert listed[0].preview_url == f"/resumes/{second.id}/file"
    assert listed[1].preview_url == f"/resumes/{first.id}/file"


def test_replace_resume_file_updates_record_and_removes_old_file(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )
        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4-first",
            )
        )
        original_path = _resolve_saved_path(created.file_path or "")

        replaced = service.replace_resume_file(
            created.id,
            UploadedResumeFile(
                filename="resume.jpg",
                content_type="image/jpeg",
                content=b"image-bytes",
            ),
        )

    assert replaced.original_filename == "resume.jpg"
    assert replaced.media_type == "image/jpeg"
    assert replaced.file_path != created.file_path
    assert not original_path.exists()
    assert _resolve_saved_path(replaced.file_path or "").exists()


def test_replace_resume_file_rejects_unsupported_file_without_touching_existing_record(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )
        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )
        original_path = _resolve_saved_path(created.file_path or "")

        with pytest.raises(UnsupportedResumeFileError, match="Unsupported resume file type"):
            service.replace_resume_file(
                created.id,
                UploadedResumeFile(
                    filename="resume.txt",
                    content_type="text/plain",
                    content=b"text",
                ),
            )

        stored = session.execute(
            text(
                "SELECT file_path, original_filename, media_type "
                "FROM tb_resume WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert stored == (created.file_path, "resume.pdf", "application/pdf")
    assert original_path.exists()
    assert len(list(temporary_resume_upload_dir.glob("*"))) == 1


def test_delete_resume_removes_database_record_and_file(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )
        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )
        saved_path = _resolve_saved_path(created.file_path or "")

        service.delete_resume(created.id)
        count = session.execute(text("SELECT COUNT(*) FROM tb_resume")).scalar_one()

    assert count == 0
    assert not saved_path.exists()


def test_get_resume_file_returns_saved_file(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )
        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )

        stored_file = service.get_resume_file(created.id)

    assert stored_file.media_type == "application/pdf"
    assert stored_file.filename == "resume.pdf"
    assert stored_file.path.exists()


def test_create_resume_from_file_rejects_empty_uploaded_file(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            upload_dir=temporary_resume_upload_dir,
        )

        with pytest.raises(EmptyResumeContentError, match="Uploaded file is empty"):
            service.create_from_file(
                UploadedResumeFile(
                    filename="resume.pdf",
                    content_type="application/pdf",
                    content=b"",
                )
            )

    assert list(temporary_resume_upload_dir.glob("*")) == []
