"""Offline native-dependency checks for the packaged desktop backend."""

from __future__ import annotations

import base64
import json
import os
import sys
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory


def check_rendered_file(file_path: Path) -> None:
    from utils.document_assets import render_file_to_images

    images = render_file_to_images(file_path)
    if not images or not all(
        base64.b64decode(image.base64_data).startswith(b"\x89PNG\r\n\x1a\n")
        for image in images
    ):
        raise RuntimeError(f"{file_path.suffix} rendering did not produce PNG images.")


def check_pdf() -> None:
    import fitz

    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "OfferPilot Linux packaging check")
        document.save("sample.pdf")
    check_rendered_file(Path("sample.pdf"))


def check_docx() -> None:
    words = import_module("aspose.words")

    document = words.Document()
    words.DocumentBuilder(document).write("OfferPilot DOCX preview / 简历预览")
    document.save("sample.docx", words.SaveFormat.DOCX)
    check_rendered_file(Path("sample.docx"))


def check_ocr() -> None:
    from rapidocr_onnxruntime import RapidOCR

    # Initialization loads the bundled ONNX models; it never downloads models.
    RapidOCR()


def run_self_check() -> int:
    checks: dict[str, Callable[[], None]] = {
        "pdf": check_pdf,
        "docx": check_docx,
        "ocr": check_ocr,
    }
    results: dict[str, dict[str, object]] = {}
    original_directory = Path.cwd()
    logger_preexisting = "utils.logger" in sys.modules
    with TemporaryDirectory(prefix="offerpilot-self-check-") as directory:
        os.chdir(directory)
        try:
            for name, check in checks.items():
                try:
                    check()
                    results[name] = {"ok": True}
                except Exception as error:
                    results[name] = {"ok": False, "error": str(error)}
        finally:
            if not logger_preexisting:
                logger = getattr(sys.modules.get("utils.logger"), "logger", None)
                if logger is not None:
                    logger.remove()
            os.chdir(original_directory)
    ok = all(result["ok"] for result in results.values())
    print(json.dumps({"ok": ok, "checks": results}, ensure_ascii=False))
    return 0 if ok else 1
