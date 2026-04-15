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
    assert created.has_file is False
    assert created.preview_url is None
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
    assert created.has_file is True
    assert created.preview_url == f"/resumes/{created.id}/file"
    assert stored[1:] == ("resume.png", "image/png", "Jane Doe\nPython Engineer")
    assert stored[0] is not None
    assert _resolve_saved_path(stored[0]).exists()


def test_list_resumes_returns_summary_in_descending_order(
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
        first = service.create_from_text("A" * 250)
        monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Second")
        second = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )

        listed = service.list_resumes()

    assert [item.id for item in listed] == [second.id, first.id]
    assert listed[0].content_preview == "Second"
    assert listed[0].preview_url == f"/resumes/{second.id}/file"
    assert listed[1].content_preview == "A" * 200
    assert listed[1].preview_url is None


def test_update_resume_text_keeps_file_metadata(
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
        monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Original")
        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )

        updated = service.update_resume_text(created.id, " Updated content ")
        stored = session.execute(
            text(
                "SELECT file_path, original_filename, media_type, content "
                "FROM tb_resume WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert updated.content == "Updated content"
    assert updated.file_path == created.file_path
    assert stored == (
        created.file_path,
        "resume.pdf",
        "application/pdf",
        "Updated content",
    )


def test_replace_resume_file_updates_record_and_removes_old_file(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed_values = iter(["First content", "Second content"])
    monkeypatch.setattr(
        DocumentParserService,
        "extract_text",
        lambda self, _: next(parsed_values),
    )

    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
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

    assert replaced.content == "Second content"
    assert replaced.original_filename == "resume.jpg"
    assert replaced.media_type == "image/jpeg"
    assert replaced.file_path != created.file_path
    assert not original_path.exists()
    assert _resolve_saved_path(replaced.file_path or "").exists()


def test_replace_resume_file_cleans_up_new_file_on_parse_failure(
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
        monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Original")
        created = service.create_from_file(
            UploadedResumeFile(
                filename="resume.pdf",
                content_type="application/pdf",
                content=b"%PDF-1.4",
            )
        )
        original_path = _resolve_saved_path(created.file_path or "")
        monkeypatch.setattr(
            DocumentParserService,
            "extract_text",
            lambda self, _: (_ for _ in ()).throw(ResumeParsingError("parse failed")),
        )

        with pytest.raises(ResumeParsingError, match="parse failed"):
            service.replace_resume_file(
                created.id,
                UploadedResumeFile(
                    filename="resume.png",
                    content_type="image/png",
                    content=b"image-bytes",
                ),
            )

        stored = session.execute(
            text(
                "SELECT file_path, original_filename, media_type, content "
                "FROM tb_resume WHERE id = :id"
            ),
            {"id": created.id},
        ).one()

    assert stored == (created.file_path, "resume.pdf", "application/pdf", "Original")
    assert original_path.exists()
    assert len(list(temporary_resume_upload_dir.glob("*"))) == 1


def test_delete_resume_removes_database_record_and_file(
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
        monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Stored")
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=temporary_resume_upload_dir,
        )
        monkeypatch.setattr(DocumentParserService, "extract_text", lambda self, _: "Stored")
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


def test_get_resume_file_for_text_resume_raises_lookup_error(
    initialized_database_manager: DatabaseManager,
    temporary_resume_upload_dir: Path,
) -> None:
    with initialized_database_manager.session_scope() as session:
        service = ResumeService(
            repository=ResumeDocumentRepository(session),
            parser=DocumentParserService(),
            upload_dir=temporary_resume_upload_dir,
        )
        created = service.create_from_text("Plain text resume")

        with pytest.raises(LookupError, match=f"Resume file not found: {created.id}"):
            service.get_resume_file(created.id)
