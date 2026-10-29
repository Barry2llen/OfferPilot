"""UTF-8 boundaries for application-owned streams and log files."""

from __future__ import annotations

import codecs
import os
import sys
from pathlib import Path
from uuid import uuid4


def configure_utf8_stdio() -> None:
    os.environ.update(
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8:backslashreplace",
        PYTHONUNBUFFERED="1",
    )
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace", write_through=True)
            except (OSError, ValueError):
                # Closed streams and test capture objects need no replacement.
                pass


def prepare_utf8_log(path: Path) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("rb") as source:
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            try:
                while chunk := source.read(64 * 1024):
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                pass
            else:
                return None
    except FileNotFoundError:
        return None
    archive = path.with_name(f"{path.name}.legacy-{uuid4().hex}")
    path.rename(archive)
    return archive
