"""Both platform branches must stay exercisable from one machine.

The Windows and macOS branches of ``platform_support``, the macOS ``.app`` builder and the
Linux menu entry are tested by patching the platform flags, so a regression on either side
is caught without owning both machines.
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cloak import platform_support as ps


def as_platform(monkeypatch, *, windows=False, macos=False):
    monkeypatch.setattr(ps, "IS_WINDOWS", windows)
    monkeypatch.setattr(ps, "IS_MACOS", macos)
    monkeypatch.setattr(ps, "IS_LINUX", not windows and not macos)


def test_documents_dir_windows_uses_known_folder(monkeypatch):
    as_platform(monkeypatch, windows=True)
    monkeypatch.setattr(ps, "_known_folder", lambda name: Path("C:/Users/demo/Documents"))
    assert ps.documents_dir() == Path("C:/Users/demo/Documents")


def test_documents_dir_macos(monkeypatch):
    as_platform(monkeypatch, macos=True)
    assert ps.documents_dir() == Path.home() / "Documents"


def test_documents_dir_linux_honours_xdg(monkeypatch, tmp_path):
    as_platform(monkeypatch)
    monkeypatch.setenv("XDG_DOCUMENTS_DIR", str(tmp_path / "文稿"))
    assert ps.documents_dir() == tmp_path / "文稿"


def test_desktop_dir_macos_and_windows(monkeypatch):
    as_platform(monkeypatch, macos=True)
    assert ps.desktop_dir() == Path.home() / "Desktop"
    as_platform(monkeypatch, windows=True)
    monkeypatch.setattr(ps, "_known_folder", lambda name: Path("C:/Users/demo/Desktop"))
    assert ps.desktop_dir() == Path("C:/Users/demo/Desktop")


def test_task_home_override_and_default(monkeypatch, tmp_path):
    monkeypatch.setenv("LPC_TASK_HOME", str(tmp_path / "任务"))
    assert ps.task_home() == tmp_path / "任务"
    monkeypatch.delenv("LPC_TASK_HOME")
    assert ps.task_home() == ps.documents_dir() / "信息隐身衣任务"


def test_windows_tool_candidates_probe_program_files(monkeypatch):
    as_platform(monkeypatch, windows=True)
    monkeypatch.delenv("LPC_TESSERACT", raising=False)
    monkeypatch.setenv("ProgramFiles", "C:/Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", "C:/Program Files (x86)")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/demo/AppData/Local")
    names = [str(item).replace("\\", "/") for item in ps._tool_candidates("tesseract")]
    assert any(name.endswith("Tesseract-OCR/tesseract.exe") for name in names)
    poppler = [str(item).replace("\\", "/") for item in ps._tool_candidates("pdftoppm")]
    assert any("poppler" in name and name.endswith("pdftoppm.exe") for name in poppler)


def test_macos_tool_candidates_include_homebrew(monkeypatch):
    as_platform(monkeypatch, macos=True)
    monkeypatch.delenv("LPC_TESSERACT", raising=False)
    candidates = [str(item) for item in ps._tool_candidates("tesseract")]
    assert "/opt/homebrew/bin/tesseract" in candidates
    assert any(name.endswith("LibreOffice.app/Contents/MacOS/soffice")
               for name in (str(item) for item in ps._tool_candidates("soffice")))


def test_linux_tool_candidates_include_usr_bin(monkeypatch):
    as_platform(monkeypatch)
    monkeypatch.delenv("LPC_TESSERACT", raising=False)
    assert any(str(item) == "/usr/bin/tesseract" for item in ps._tool_candidates("tesseract"))


def test_open_folder_macos_uses_open(monkeypatch, tmp_path):
    as_platform(monkeypatch, macos=True)
    calls = []
    monkeypatch.setattr(ps.subprocess, "run",
                        lambda args, **kw: calls.append(args) or subprocess.CompletedProcess(args, 0))
    ps.open_folder(tmp_path)
    assert calls == [["/usr/bin/open", str(tmp_path)]]


def test_open_folder_windows_uses_startfile(monkeypatch, tmp_path):
    as_platform(monkeypatch, windows=True)
    seen = []
    monkeypatch.setattr(os, "startfile", lambda path: seen.append(path), raising=False)
    ps.open_folder(tmp_path)
    assert seen == [str(tmp_path)]


def test_reveal_folder_macos_selects_item(monkeypatch, tmp_path):
    as_platform(monkeypatch, macos=True)
    calls = []
    monkeypatch.setattr(ps.subprocess, "run",
                        lambda args, **kw: calls.append(args) or subprocess.CompletedProcess(args, 0))
    ps.reveal_folder(tmp_path / "交付.docx")
    assert calls == [["/usr/bin/open", "-R", str(tmp_path / "交付.docx")]]


def test_secure_fd_is_safe_where_fchmod_missing(monkeypatch):
    monkeypatch.delattr(os, "fchmod", raising=False)
    ps.secure_fd(1)


def test_path_warning_only_on_windows(monkeypatch, tmp_path):
    long = tmp_path / ("深" * 220 + ".docx")
    as_platform(monkeypatch, macos=True)
    assert ps.path_length_warning(long) == ""
    as_platform(monkeypatch, windows=True)
    assert "260" in ps.path_length_warning(long)


def test_macos_app_bundle_structure(tmp_path):
    import build_app

    target = tmp_path / "信息隐身衣.app"
    build_app.build(target, ROOT)
    plist = plistlib.loads((target / "Contents" / "Info.plist").read_bytes())
    assert plist["CFBundleShortVersionString"] == build_app.VERSION
    assert plist["LSMinimumSystemVersion"] == "11.0"
    assert plist["CFBundleExecutable"] == "launch"
    assert plist["CFBundleIconFile"] == "Icon.icns"
    launcher = (target / "Contents" / "MacOS" / "launch").read_text("utf-8")
    assert "run.sh" in launcher and "Library/Logs" in launcher
    assert os.access(target / "Contents" / "MacOS" / "launch", os.X_OK)
    assert (target / "Contents" / "Resources" / "Icon.icns").stat().st_size > 1000


def test_macos_app_bundle_rejects_existing_target(tmp_path):
    import build_app

    target = tmp_path / "exists.app"
    target.mkdir()
    with pytest.raises(ValueError) as error:
        build_app.build(target, ROOT)
    assert str(error.value) == "APP_TARGET_EXISTS"


def test_linux_desktop_entry_quotes_exec(monkeypatch, tmp_path):
    import install

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    entry = install.linux_shortcut(ROOT / "信息隐身衣 测试")
    text = entry.read_text("utf-8")
    assert 'Exec="' in text and "run.sh" in text
    assert "Terminal=false" in text
    assert os.access(entry, os.X_OK)


def test_both_launchers_target_the_same_entrypoint():
    posix = (ROOT / "信息隐身衣.command").read_text("utf-8")
    windows = (ROOT / "信息隐身衣.cmd").read_text("utf-8")
    assert "scripts/run.sh" in posix and "desktop" in posix
    assert "scripts\\run.cmd" in windows and "desktop" in windows
