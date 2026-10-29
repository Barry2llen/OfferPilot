import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from utils.stdio import configure_utf8_stdio, prepare_utf8_log


def test_stdio_reconfigures_legacy_pipes_without_losing_unicode(monkeypatch):
    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding="gbk")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    configure_utf8_stdio()
    configure_utf8_stdio()
    stream.write("中文😀\ud800")
    assert output.getvalue().decode("utf-8") == "中文😀\\ud800"
    assert os.environ["PYTHONIOENCODING"] == "utf-8:backslashreplace"


@pytest.mark.parametrize("kind", ["none", "capture", "closed"])
def test_stdio_tolerates_missing_closed_and_capture_streams(monkeypatch, kind):
    stream = None if kind == "none" else io.StringIO()
    if kind == "closed":
        stream = io.TextIOWrapper(io.BytesIO())
        stream.close()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    configure_utf8_stdio()
    assert sys.stdout is stream


def test_legacy_logs_are_archived_without_rewriting_bytes(tmp_path):
    path = tmp_path / "中文" / "runtime.log"
    path.parent.mkdir()
    legacy = "旧日志".encode("gbk")
    path.write_bytes(legacy)
    archive = prepare_utf8_log(path)
    assert archive is not None
    assert archive.read_bytes() == legacy
    assert not path.exists()
    path.write_text("新日志😀", encoding="utf-8")
    assert prepare_utf8_log(path) is None
    assert path.read_text(encoding="utf-8") == "新日志😀"
    assert prepare_utf8_log(tmp_path / "missing.log") is None


def test_backend_logging_and_redirected_streams_are_utf8(tmp_path):
    backend = Path(__file__).resolve().parents[2]
    environment = {
        **os.environ,
        "PYTHONPATH": str(backend),
        "PYTHONIOENCODING": "gbk",
        "PYTHONUTF8": "0",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from utils.logger import logger; import sys; "
            "print('中文😀'); print('错误😀', file=sys.stderr); "
            "logger.info('文件日志😀')",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert "中文😀" in result.stdout.decode("utf-8", errors="strict")
    assert "错误😀" in result.stderr.decode("utf-8", errors="strict")
    assert "文件日志😀" in (tmp_path / "logs/runtime.log").read_text(encoding="utf-8")
