from pathlib import Path

import pytest
from sqlalchemy import text

from db.engine import DatabaseManager
from db.repositories import ResumeDocumentRepository
from services.document_parser_service import DocumentParserService, ResumeParsingError
from services.resume_service import (
    EmptyResumeContentError,
    ResumeService,
    UploadedResumeFile,
)


@pytest.fixture
def initialized_database_manager(
    temporary_database_manager: DatabaseManager,
) -> DatabaseManager:
    temporary_database_manager.initialize_tables()
    return temporary_database_manager


def _resolve_saved_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else Path.cwd() / path


def test_create_resume_from_text(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=temporary_resume_upload_dir,
        )
        created = service.create_from_text("  Jane Doe Resume  ")
        stored = session.execute(
            text("SELECT file_path, content FROM tb_resume WHERE id = :id"),
            {"id": created.id},
        ).one()

    assert created.file_path is None
    assert created.content == "Jane Doe Resume"
    assert stored == (None, "Jane Doe Resume")


def test_create_resume_from_file_persists_metadata(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=temporary_resume_upload_dir,
        )
        monkeypatch.setattr(
            DocumentParserService,
            "extract_text",
            lambda self, _: "Jane Doe\nPython Engineer",
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
                "SELECT file_path, original_filename, media_type, content "
                "FROM tb_resume WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert created.original_filename == "resume.png"
    assert created.media_type == "image/png"
    assert stored[1:] == ("resume.png", "image/png", "Jane Doe\nPython Engineer")
    assert stored[0] is not None
    assert _resolve_saved_path(stored[0]).exists()


def test_create_resume_from_file_cleans_up_on_parse_failure(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=temporary_resume_upload_dir,
        )
        monkeypatch.setattr(
            DocumentParserService,
            "extract_text",
            lambda self, _: (_ for _ in ()).throw(ResumeParsingError("parse failed")),
        )

        with pytest.raises(ResumeParsingError, match="parse failed"):
            service.create_from_file(
                UploadedResumeFile(
                    filename="resume.pdf",
                    content_type="application/pdf",
                    content=b"%PDF-1.4",
                )
            )

    assert not temporary_resume_upload_dir.exists() or not any(
        temporary_resume_upload_dir.iterdir()
    )


def test_create_resume_rejects_blank_text(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=temporary_resume_upload_dir,
        )

        with pytest.raises(EmptyResumeContentError, match="Resume content is empty"):
            service.create_from_text("   \n  ")
