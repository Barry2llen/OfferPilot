import secrets
from dataclasses import dataclass
from pathlib import Path

from langchain_core.messages import HumanMessage

from db.models import ChatFileORM, ChatThreadFileORM
from db.repositories import ChatFileRepository, ChatThreadFileRepository
from exceptions import (
    ChatFileNotFoundError,
    ChatFileProcessingError,
    EmptyChatFileContentError,
    ResumeParsingError,
    ResumePreviewConversionError,
    ResumePreviewDependencyError,
    ResumePreviewError,
    ResumeValidationError,
    UnsupportedChatFileError,
    UnsupportedResumeFileError,
)
from schemas.chat_file import ChatAttachmentRef, ChatFileDetail, ChatFileListItem, StoredChatFile
from schemas.model_selection import ModelSelection
from utils.document_assets import (
    decode_text_file,
    extract_ocr_text,
    is_chat_image_document,
    is_supported_chat_file_suffix,
    is_textual_chat_file,
    render_file_to_images,
)

_FILE_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(slots=True)
class UploadedChatFile:
    filename: str
    content_type: str | None
    content: bytes


@dataclass(slots=True)
class PreparedChatPrompt:
    human_message: HumanMessage
    attachments: list[ChatAttachmentRef]
    requires_image_input: bool
    attachment_count: int
    created_file_paths: list[Path]


@dataclass(slots=True)
class StoredChatFiles:
    records: list[ChatFileORM]
    created_file_paths: list[Path]


class ChatFileService:
    """Service for chat attachment storage, prompt injection, and cleanup."""

    def __init__(
        self,
        file_repository: ChatFileRepository,
        thread_file_repository: ChatThreadFileRepository,
        upload_dir: str | Path,
    ) -> None:
        self._file_repository = file_repository
        self._thread_file_repository = thread_file_repository
        self._upload_dir = Path(upload_dir)

    def list_files(self) -> list[ChatFileListItem]:
        return [
            self._to_list_item(record, reference_count)
            for record, reference_count in self._file_repository.list_all_with_reference_count()
        ]

    def get_file_detail(self, file_id: str) -> ChatFileDetail:
        row = self._file_repository.get_with_reference_count(file_id)
        if row is None:
            raise ChatFileNotFoundError(f"Chat file not found: {file_id}")
        record, reference_count = row
        return ChatFileDetail(**self._to_list_item(record, reference_count).model_dump())

    def get_file_raw(self, file_id: str) -> StoredChatFile:
        record = self._file_repository.get_by_id(file_id)
        if record is None:
            raise ChatFileNotFoundError(f"Chat file not found: {file_id}")

        return StoredChatFile(
            path=str(self._resolve_storage_path(record.storage_path)),
            media_type=record.media_type,
            filename=record.original_filename,
        )

    def store_files(self, uploaded_files: list[UploadedChatFile]) -> StoredChatFiles:
        created_file_paths: list[Path] = []
        records: list[ChatFileORM] = []
        try:
            for uploaded_file in uploaded_files:
                stored = self._create_file_record(uploaded_file)
                records.append(stored)
                created_file_paths.append(
                    self._resolve_storage_path(stored.storage_path, require_exists=False)
                )
        except Exception:
            for path in created_file_paths:
                self._delete_file_quietly(path)
            raise

        return StoredChatFiles(records=records, created_file_paths=created_file_paths)

    def prepare_prompt(
        self,
        *,
        thread_id: str,
        selection: ModelSelection,
        prompt: str,
        file_ids: list[str],
        uploaded_files: list[UploadedChatFile],
    ) -> PreparedChatPrompt:
        normalized_prompt = prompt.strip()

        created_file_paths: list[Path] = []
        try:
            stored_records: list[ChatFileORM] = []
            for uploaded_file in uploaded_files:
                stored = self._create_file_record(uploaded_file)
                stored_records.append(stored)
                created_file_paths.append(
                    self._resolve_storage_path(stored.storage_path, require_exists=False)
                )

            for file_id in file_ids:
                record = self._file_repository.get_by_id(file_id)
                if record is None:
                    raise ChatFileNotFoundError(f"Chat file not found: {file_id}")
                stored_records.append(record)

            if not stored_records:
                if not normalized_prompt:
                    raise ResumeValidationError(
                        "Prompt or at least one attachment is required for chat requests."
                    )
                return PreparedChatPrompt(
                    human_message=HumanMessage(content=normalized_prompt),
                    attachments=[],
                    requires_image_input=self.thread_requires_image_input(thread_id),
                    attachment_count=self._thread_file_repository.count_by_thread(thread_id),
                    created_file_paths=created_file_paths,
                )

            attachments: list[ChatAttachmentRef] = []
            content_blocks: list[dict[str, object]] = []
            reference_lines: list[str] = []

            for record in stored_records:
                thread_record = self._thread_file_repository.get(thread_id, record.id)
                is_new_to_thread = thread_record is None
                injection_mode = (
                    thread_record.injection_mode
                    if thread_record is not None
                    else self._resolve_injection_mode(record, selection)
                )
                if is_new_to_thread:
                    self._thread_file_repository.create(
                        ChatThreadFileORM(
                            thread_id=thread_id,
                            file_id=record.id,
                            injection_mode=injection_mode,
                        )
                    )

                attachment = ChatAttachmentRef(
                    file_id=record.id,
                    original_filename=record.original_filename,
                    media_type=record.media_type,
                    injection_mode=injection_mode,
                )
                attachments.append(attachment)
                reference_lines.append(
                    f"- {attachment.file_id} ({attachment.original_filename}, mode={attachment.injection_mode})"
                )

                if not is_new_to_thread:
                    continue

                try:
                    if injection_mode == "image":
                        content_blocks.extend(self._build_image_blocks(record))
                    else:
                        extracted_text = self._extract_attachment_text(record, injection_mode)
                        content_blocks.append(
                            {
                                "type": "text",
                                "text": self._build_attachment_text_block(
                                    attachment,
                                    extracted_text,
                                    injection_mode,
                                ),
                            }
                        )
                except (
                    UnsupportedResumeFileError,
                    ResumeParsingError,
                    ResumePreviewError,
                ) as error:
                    raise ChatFileProcessingError(str(error)) from error

            content_blocks.insert(
                0,
                {
                    "type": "text",
                    "text": self._build_visible_prompt(normalized_prompt, reference_lines),
                },
            )

            requires_image_input = self.thread_requires_image_input(thread_id)
            return PreparedChatPrompt(
                human_message=HumanMessage(
                    content=content_blocks,
                    additional_kwargs={
                        "display_content": normalized_prompt,
                        "attachments": [
                            attachment.model_dump(mode="json") for attachment in attachments
                        ],
                        "requires_image_input": requires_image_input,
                    },
                ),
                attachments=attachments,
                requires_image_input=requires_image_input,
                attachment_count=self._thread_file_repository.count_by_thread(thread_id),
                created_file_paths=created_file_paths,
            )
        except Exception:
            for path in created_file_paths:
                self._delete_file_quietly(path)
            raise

    def thread_requires_image_input(self, thread_id: str) -> bool:
        return self._thread_file_repository.has_image_mode(thread_id)

    def delete_thread_attachments(self, thread_id: str) -> None:
        file_ids = self._thread_file_repository.delete_by_thread(thread_id)
        for file_id in file_ids:
            if self._thread_file_repository.count_references_for_file(file_id) > 0:
                continue

            record = self._file_repository.get_by_id(file_id)
            if record is None:
                continue

            resolved_path = self._resolve_storage_path(
                record.storage_path,
                require_exists=False,
            )
            self._file_repository.delete(file_id)
            self._delete_file_quietly(resolved_path)

    def _create_file_record(self, uploaded_file: UploadedChatFile) -> ChatFileORM:
        filename = Path(uploaded_file.filename).name
        if not filename:
            raise ResumeValidationError("Uploaded file name is required.")
        if not uploaded_file.content:
            raise EmptyChatFileContentError("Uploaded chat file is empty.")

        suffix = Path(filename).suffix.lower()
        if suffix == ".doc":
            raise UnsupportedChatFileError("Legacy .doc files are not supported.")
        if not is_supported_chat_file_suffix(suffix):
            raise UnsupportedChatFileError(
                f"Unsupported chat file type: {suffix or '<missing>'}"
            )

        saved_path = self._upload_dir / f"{secrets.token_hex(16)}{suffix}"
        saved_path.parent.mkdir(parents=True, exist_ok=True)
        saved_path.write_bytes(uploaded_file.content)

        try:
            for _ in range(16):
                file_id = self._generate_file_id()
                if self._file_repository.get_by_id(file_id) is not None:
                    continue
                return self._file_repository.create(
                    ChatFileORM(
                        id=file_id,
                        storage_path=self._to_storage_path(saved_path),
                        original_filename=filename,
                        media_type=uploaded_file.content_type,
                        size_bytes=len(uploaded_file.content),
                    )
                )
        except Exception:
            saved_path.unlink(missing_ok=True)
            raise

        saved_path.unlink(missing_ok=True)
        raise ChatFileProcessingError("Failed to allocate a unique chat file id.")

    def _resolve_injection_mode(
        self,
        record: ChatFileORM,
        selection: ModelSelection,
    ) -> str:
        file_path = self._resolve_storage_path(record.storage_path)
        if is_textual_chat_file(file_path):
            return "text"
        if is_chat_image_document(file_path) and selection.supports_image_input:
            return "image"
        if is_chat_image_document(file_path):
            return "ocr_text"
        raise UnsupportedChatFileError(
            f"Unsupported chat file type: {file_path.suffix.lower() or '<missing>'}"
        )

    def _build_image_blocks(self, record: ChatFileORM) -> list[dict[str, object]]:
        file_path = self._resolve_storage_path(record.storage_path)
        images = render_file_to_images(file_path)
        return [image.to_content_block() for image in images]

    def _extract_attachment_text(self, record: ChatFileORM, injection_mode: str) -> str:
        file_path = self._resolve_storage_path(record.storage_path)
        if injection_mode == "text":
            return decode_text_file(file_path)
        if injection_mode == "ocr_text":
            return extract_ocr_text(file_path)
        raise ChatFileProcessingError(f"Unsupported injection mode: {injection_mode}")

    def _build_visible_prompt(self, prompt: str, reference_lines: list[str]) -> str:
        references = "\n".join(reference_lines)
        visible_prompt = prompt or "请分析这些附件内容。"
        return f"{visible_prompt}\n\n[附件引用]\n{references}"

    def _build_attachment_text_block(
        self,
        attachment: ChatAttachmentRef,
        extracted_text: str,
        injection_mode: str,
    ) -> str:
        label = "OCR 文本" if injection_mode == "ocr_text" else "文本内容"
        return (
            f"[附件 {attachment.file_id} | {attachment.original_filename} | {label}]\n"
            f"{extracted_text}"
        )

    def _to_list_item(self, record: ChatFileORM, reference_count: int) -> ChatFileListItem:
        return ChatFileListItem(
            id=record.id,
            original_filename=record.original_filename,
            media_type=record.media_type,
            size_bytes=record.size_bytes,
            created_at=record.created_at,
            reference_count=reference_count,
            raw_url=f"/ai/files/{record.id}/raw",
        )

    def _generate_file_id(self) -> str:
        return "".join(secrets.choice(_FILE_ID_ALPHABET) for _ in range(6))

    def _to_storage_path(self, file_path: Path) -> str:
        resolved_path = file_path.resolve()
        try:
            return resolved_path.relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            return resolved_path.as_posix()

    def _resolve_storage_path(
        self,
        file_path: str,
        *,
        require_exists: bool = True,
    ) -> Path:
        candidate = Path(file_path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (Path.cwd() / candidate).resolve()
        )
        allowed_roots = (Path.cwd().resolve(), self._upload_dir.resolve())
        if not any(self._is_relative_to(resolved, root) for root in allowed_roots):
            raise ChatFileNotFoundError("Chat file not found.")
        if require_exists and not resolved.is_file():
            raise ChatFileNotFoundError("Chat file not found.")
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
