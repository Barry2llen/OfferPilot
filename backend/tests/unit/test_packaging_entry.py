import json
import sys

import pytest

from scripts import electron_api_entry, packaging_self_check


def test_self_check_does_not_start_server_or_create_runtime(monkeypatch, tmp_path):
    runtime = tmp_path / "unused-runtime"
    monkeypatch.setattr(
        sys, "argv", ["offer-pilot-api", "--self-check", "--runtime-dir", str(runtime)]
    )
    monkeypatch.setattr(packaging_self_check, "run_self_check", lambda: 0)
    monkeypatch.setattr(
        electron_api_entry.uvicorn,
        "run",
        lambda *args, **kwargs: pytest.fail("self-check must not start HTTP"),
    )
    assert electron_api_entry.main() == 0
    assert not runtime.exists()


@pytest.mark.parametrize("failure", [None, "pdf", "docx", "ocr"])
def test_self_check_reports_results_and_failure_exit(monkeypatch, capsys, failure):
    called = []

    def check(name):
        def run():
            called.append(name)
            if name == failure:
                raise RuntimeError(f"missing {name} runtime")

        return run

    for name in ["pdf", "docx", "ocr"]:
        monkeypatch.setattr(packaging_self_check, f"check_{name}", check(name))
    assert packaging_self_check.run_self_check() == (1 if failure else 0)
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is (failure is None)
    assert called == ["pdf", "docx", "ocr"]
    if failure:
        assert result["checks"][failure] == {
            "ok": False,
            "error": f"missing {failure} runtime",
        }
