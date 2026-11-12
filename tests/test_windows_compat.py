"""Cross-platform regressions: everything here broke on Windows at least once.

Only synthetic content is used; no real material is opened.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cloak import platform_support as ps
from cloak.vault import open_vault, seal

PW = "SYNTHETIC-windows-compat-2026"


def test_atomic_write_without_fchmod(monkeypatch, tmp_path):
    """Windows has no os.fchmod; the vault write must still work."""
    monkeypatch.delattr(os, "fchmod", raising=False)
    target = tmp_path / "任务 空格" / "task.lpcv"
    seal(target, {"files": [], "task": "abc123"}, PW)
    assert open_vault(target, PW)["task"] == "abc123"


def test_secure_fd_is_noop_when_fchmod_missing(monkeypatch):
    monkeypatch.delattr(os, "fchmod", raising=False)
    ps.secure_fd(0, 0o600)  # must not raise


def test_atomic_write_replaces_existing_file(tmp_path):
    target = tmp_path / "report.json"
    ps.atomic_write(target, b'{"a":1}')
    ps.atomic_write(target, b'{"a":2}')
    assert json.loads(target.read_text())["a"] == 2


def test_long_path_is_absolute_and_usable(tmp_path):
    path = ps.long_path(tmp_path / "nested" / "file.txt")
    assert os.path.isabs(path)
    if os.name != "nt":
        assert path == str((tmp_path / "nested" / "file.txt").resolve())


def test_timezone_works_without_iana_database():
    from datetime import datetime
    tz = ps.shanghai_tz()
    assert datetime.now(tz).utcoffset() == timedelta(hours=8)


def test_documents_and_desktop_dirs_are_paths():
    assert isinstance(ps.documents_dir(), Path)
    assert isinstance(ps.desktop_dir(), Path)


def test_resolve_tool_returns_path_or_none():
    for name in ("tesseract", "pdftoppm", "soffice"):
        value = ps.resolve_tool(name)
        assert value is None or Path(value).exists()
    assert set(ps.tool_status()) == {"tesseract", "pdftoppm", "soffice"}


def test_tesseract_languages_never_raises(monkeypatch):
    monkeypatch.setattr(ps, "resolve_tool", lambda name: None)
    assert ps.tesseract_languages() == []


def test_run_tool_missing_binary_maps_to_local_tool_unavailable():
    with pytest.raises(ValueError) as error:
        ps.run_tool([str(Path(os.devnull))])  # not an executable
    assert str(error.value) == "LOCAL_TOOL_UNAVAILABLE"


def test_open_folder_reports_stable_code(monkeypatch, tmp_path):
    """The stable error code must hold on every platform, whatever opener is used.

    macOS calls /usr/bin/open directly and never consults shutil.which, so mocking the
    opener call itself keeps this test valid on macOS, Linux and Windows alike.
    """
    def fail(*args, **kwargs):
        raise OSError("simulated opener failure")

    monkeypatch.setattr(ps.shutil, "which", lambda name: None)
    monkeypatch.setattr(ps.subprocess, "run", fail)
    monkeypatch.setattr(ps.os, "startfile", fail, raising=False)
    with pytest.raises(ValueError) as error:
        ps.open_folder(tmp_path)
    assert str(error.value) == "FOLDER_OPEN_FAILED"


def test_file_lock_is_exclusive_and_reusable(tmp_path):
    first = ps.FileLock(tmp_path / "launch.lock")
    second = ps.FileLock(tmp_path / "launch.lock")
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_configure_stdio_keeps_working():
    ps.configure_stdio()
    print("中文输出测试")
    sys.stderr.flush()


def test_text_encoding_error_is_a_stable_code():
    from cloak.formats import Document
    with pytest.raises(ValueError) as error:
        Document("身份证：110101199001010010".encode("gbk"), ".txt")
    assert str(error.value) == "TEXT_ENCODING_UNSUPPORTED"


def test_gbk_file_is_rejected_not_silently_reencoded():
    from cloak.formats import Document
    payload = "原告：赵测试".encode("gb18030")
    with pytest.raises(ValueError):
        Document(payload, ".md")


def test_model_status_shape():
    status = ps.model_status()
    assert set(status) >= {"spacy", "model_package", "model_path"}


def test_batch_launchers_are_ascii_crlf():
    for name in ("信息隐身衣.cmd", "scripts/run.cmd"):
        raw = (ROOT / name).read_bytes()
        assert b"\r\n" in raw, name + " must use CRLF"
        assert all(byte < 128 for byte in raw), name + " must stay ASCII for cmd.exe"
    raw = (ROOT / "scripts/run.ps1").read_bytes()
    assert b"\r\n" in raw


def test_powershell_launcher_exists_for_windows():
    text = (ROOT / "scripts/run.ps1").read_text("utf-8")
    assert "run.py" in text and "-3.12" in text


def test_base_requirements_do_not_block_on_github():
    text = (ROOT / "requirements.txt").read_text("utf-8")
    assert "github.com" not in text
    assert "tzdata" in text
    assert "zh_core_web_sm" in (ROOT / "requirements-model.txt").read_text("utf-8")


def test_wizard_uses_portable_dialog():
    text = (ROOT / "scripts/cloak/wizard.py").read_text("utf-8")
    assert "osascript" not in text
    assert "tkinter" in text and "task_home" in text


def test_desktop_opens_folders_through_platform_layer():
    text = (ROOT / "scripts/cloak/desktop.py").read_text("utf-8")
    assert "open_folder(" in text
    assert "xdg-open" not in text


def test_doctor_reports_platform_and_tools():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/lpc.py"), "doctor"],
                            capture_output=True, text=True, timeout=300, check=False,
                            encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr[-800:]
    report = json.loads(result.stdout)
    assert report["status"] in ("READY", "DEPENDENCIES_MISSING")
    assert report["platform"]
    assert set(report["programs"]) == {"tesseract", "pdftoppm", "soffice"}
    assert report["ner"] in ("READY", "RULES_ONLY", "MISSING")


def test_rule_only_mode_requires_explicit_opt_in(tmp_path, monkeypatch):
    """Without the opt-in the engine still fails closed; with it, a review issue appears."""
    from cloak.core import Detector
    from cloak.workflow import require_ner

    detector = Detector(use_ner=False)
    monkeypatch.setenv("LPC_RUNTIME_HOME", str(tmp_path / "runtime"))
    monkeypatch.delenv("LPC_ALLOW_RULE_ONLY", raising=False)
    with pytest.raises(ValueError) as error:
        require_ner(detector)
    assert str(error.value) == "LOCAL_NER_UNAVAILABLE"

    monkeypatch.setenv("LPC_ALLOW_RULE_ONLY", "1")
    assert require_ner(detector) is True


def test_release_self_check_passes():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/check_release.py")],
                            capture_output=True, text=True, timeout=300, check=False,
                            encoding="utf-8", errors="replace")
    report = json.loads(result.stdout or "{}")
    assert report.get("status") == "PASS", report.get("errors")


def test_bootstrap_help_runs_standalone():
    result = subprocess.run([sys.executable, str(ROOT / "scripts/bootstrap.py"), "--help"],
                            capture_output=True, text=True, timeout=180, check=False,
                            encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr[-800:]
    assert "--reuse-system" in result.stdout and "--rule-only" in result.stdout


def test_rule_only_scan_marks_every_file(tmp_path, monkeypatch):
    """A missing model must be visible in the task, not silently ignored."""
    from cloak import core, workflow

    def unavailable():
        raise OSError("model missing")

    monkeypatch.setattr(core, "local_model", unavailable)
    monkeypatch.setenv("LPC_ALLOW_RULE_ONLY", "1")
    source = tmp_path / "合成材料.txt"
    source.write_text("原告：赵测试，电话：13812345678", "utf-8")
    workspace = tmp_path / "任务"
    report = workflow.scan([source], workspace, PW)
    assert report["ner"] is False
    job = open_vault(workspace / "private" / "task.lpcv", PW)
    assert job["ner"] is False
    assert "RULE_ONLY_DETECTION" in job["files"][0]["issues"]
    assert "RULE_ONLY_DETECTION" in workflow.SOFT_ISSUES

    confirmations = [i for i in workflow.SOFT_ISSUES if i != "RULE_ONLY_DETECTION"]
    with pytest.raises(ValueError) as error:
        workflow.review_update(job, confirmations=confirmations)
    assert str(error.value) == "LOCAL_REVIEW_INCOMPLETE"
    workflow.review_update(job, confirmations=list(workflow.SOFT_ISSUES))
    assert job["reviewed"] is True


def test_doctor_reports_rule_only_mode(tmp_path, monkeypatch):
    import importlib
    lpc = importlib.import_module("lpc")
    monkeypatch.setenv("LPC_RUNTIME_HOME", str(tmp_path / "runtime"))
    from runtime import write_config
    write_config({"allow_rule_only": True})
    monkeypatch.setattr(lpc.ps, "model_status",
                        lambda: {"spacy": False, "model_package": False, "model_path": ""})
    report = lpc.doctor()
    assert report["ner"] == "RULES_ONLY"
    assert report["rule_only_allowed"] is True
    assert report["status"] == "READY"
    assert any("中文实体识别" in warning for warning in report["warnings"])
