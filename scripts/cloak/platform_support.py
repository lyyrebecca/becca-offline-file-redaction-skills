"""Cross-platform parity helpers for Windows, macOS and Linux.

Every OS-specific operation of the local engine goes through this module so that the
same code path runs on all three platforms:

* file creation with restrictive permissions (POSIX ``chmod``/``fchmod`` vs. Windows ACL
  inheritance; ``os.fchmod`` does not exist on Windows at all),
* atomic replacement that survives Windows file locking and 260-character path limits,
* opening the local file manager (``os.startfile`` / ``open`` / ``xdg-open``),
* locating OCR and conversion programs installed outside ``PATH`` (normal on Windows),
* UTF-8 console output and Windows console code pages,
* IANA time zone data, which Windows does not ship,
* single-instance locking (``msvcrt`` vs. ``fcntl``).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import timedelta, timezone
from pathlib import Path

IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')
PLATFORM_LABEL = {'win32': 'Windows', 'darwin': 'macOS'}.get(sys.platform, 'Linux' if IS_LINUX else sys.platform)

# Windows hides console windows for child processes unless this flag is set.
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if IS_WINDOWS else 0


def configure_stdio() -> None:
    """Make Chinese diagnostics printable on a cp936/gbk console without crashing."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding='utf-8', errors='replace')
        except (ValueError, OSError):
            pass


# --------------------------------------------------------------------------- paths

def long_path(path) -> str:
    """Return a filesystem string that also works for paths over 260 characters on Windows."""
    text = os.path.abspath(str(path))
    if not IS_WINDOWS:
        return text
    if text.startswith('\\\\?\\'):
        return text
    if len(text) < 240:
        return text
    if text.startswith('\\\\'):
        return '\\\\?\\UNC\\' + text[2:]
    return '\\\\?\\' + text


def path_length_warning(path) -> str:
    text = os.path.abspath(str(path))
    if IS_WINDOWS and len(text) > 200:
        return 'Windows 路径较长（超过200字符），可能受260字符限制影响；建议把技能目录或任务目录移到较短的路径。'
    return ''


def secure_dir(path, mode: int = 0o700) -> Path:
    """Create a directory; POSIX permissions are best-effort, Windows inherits the user ACL."""
    directory = Path(path)
    try:
        os.makedirs(long_path(directory), exist_ok=True)
    except FileExistsError:
        pass
    if not IS_WINDOWS:
        try:
            os.chmod(directory, mode)
        except OSError:
            pass
    return directory


def secure_fd(fd: int, mode: int = 0o600) -> None:
    """``os.fchmod`` is POSIX-only; Windows has no equivalent and must not crash here."""
    chmod = getattr(os, 'fchmod', None)
    if chmod is None:
        return
    try:
        chmod(fd, mode)
    except OSError:
        pass


def secure_file(path, mode: int = 0o600) -> None:
    if IS_WINDOWS:
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def atomic_write(path, data: bytes) -> None:
    """Write-then-rename so a crash never leaves a half-written vault or report."""
    target = Path(path)
    secure_dir(target.parent)
    fd, temporary = tempfile.mkstemp(prefix='.lpc-', dir=long_path(target.parent))
    try:
        secure_fd(fd)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Antivirus and search indexers briefly hold handles on Windows; a short retry
        # avoids a spurious failure while still surfacing a genuinely locked destination.
        for attempt in range(6):
            try:
                os.replace(temporary, long_path(target))
                break
            except PermissionError:
                if attempt == 5 or not IS_WINDOWS:
                    raise
                time.sleep(0.15 * (attempt + 1))
    finally:
        try:
            if os.path.exists(temporary):
                os.unlink(temporary)
        except OSError:
            pass


def remove_quietly(path) -> None:
    """Delete a temporary file; on Windows a scanner may hold it briefly."""
    for attempt in range(4):
        try:
            os.unlink(long_path(path))
            return
        except FileNotFoundError:
            return
        except OSError:
            if not IS_WINDOWS or attempt == 3:
                return
            time.sleep(0.2 * (attempt + 1))


def read_bytes(path) -> bytes:
    with open(long_path(path), 'rb') as handle:
        return handle.read()


# ------------------------------------------------------------------- known folders

_FOLDER_IDS = {
    'documents': '{FDD39AD0-238F-46AF-ADB4-6C85480369C7}',
    'desktop': '{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}',
    'downloads': '{374DE290-123F-4565-9164-39C4925E467B}',
}


def _known_folder(name: str) -> Path | None:
    """Ask Windows for the real folder (respects OneDrive redirection and localized names)."""
    if not IS_WINDOWS:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', ctypes.c_ulong), ('Data2', ctypes.c_ushort),
                        ('Data3', ctypes.c_ushort), ('Data4', ctypes.c_ubyte * 8)]

        raw = _FOLDER_IDS[name]
        guid = GUID()
        ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(raw), ctypes.byref(guid))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except (AttributeError, OSError, ValueError):
        return None


def documents_dir() -> Path:
    if IS_WINDOWS:
        found = _known_folder('documents')
        if found:
            return found
        return Path(os.environ.get('USERPROFILE', Path.home())) / 'Documents'
    if IS_MACOS:
        return Path.home() / 'Documents'
    xdg = os.environ.get('XDG_DOCUMENTS_DIR', '')
    if xdg.startswith('$HOME'):
        return Path.home() / xdg[5:].lstrip('/')
    if xdg:
        return Path(xdg)
    return Path.home() / 'Documents'


def desktop_dir() -> Path:
    if IS_WINDOWS:
        found = _known_folder('desktop')
        return found or Path.home() / 'Desktop'
    return Path.home() / 'Desktop'


def task_home() -> Path:
    """Default task folder.

    ``LPC_TASK_HOME`` matters on Windows when Documents is redirected to OneDrive or is
    protected by Defender Controlled Folder Access, which can block new folders there.
    """
    override = os.environ.get('LPC_TASK_HOME', '').strip()
    if override:
        return Path(override).expanduser()
    return documents_dir() / '信息隐身衣任务'


# ------------------------------------------------------------------------- programs

_SKILL_ROOT = Path(__file__).resolve().parents[2]
_TOOL_NAMES = {'tesseract': 'tesseract.exe', 'pdftoppm': 'pdftoppm.exe', 'soffice': 'soffice.exe'}
_TOOL_ENV = {'tesseract': 'LPC_TESSERACT', 'pdftoppm': 'LPC_PDFTOPPM', 'soffice': 'LPC_SOFFICE'}


def _tool_candidates(name: str) -> list[Path]:
    exe = _TOOL_NAMES.get(name, name + ('.exe' if IS_WINDOWS else ''))
    candidates: list[Path] = []
    override = os.environ.get(_TOOL_ENV.get(name, ''), '')
    if override:
        candidates.append(Path(override))
    # A portable tool folder inside the skill keeps OCR usable without system installers.
    for base in (_SKILL_ROOT / 'tools', _SKILL_ROOT / 'vendor' / 'tools'):
        candidates += [base / exe, base / 'bin' / exe, base / name / exe, base / name / 'bin' / exe]
    if IS_WINDOWS:
        program_files = [os.environ.get('ProgramFiles', r'C:\Program Files'),
                         os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                         os.environ.get('LOCALAPPDATA', '')]
        if name == 'tesseract':
            candidates += [Path(p) / 'Tesseract-OCR' / exe for p in program_files if p]
            candidates += [Path(p) / 'Programs' / 'Tesseract-OCR' / exe for p in program_files if p]
        elif name == 'pdftoppm':
            for p in program_files:
                if not p:
                    continue
                candidates += [Path(p) / 'poppler' / 'Library' / 'bin' / exe,
                               Path(p) / 'poppler' / 'bin' / exe,
                               Path(p) / 'poppler-24.02.0' / 'Library' / 'bin' / exe]
            candidates += [Path(r'C:\poppler\bin') / exe, Path(r'C:\ProgramData\chocolatey\bin') / exe]
            candidates += [Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Links' / exe]
        elif name == 'soffice':
            candidates += [Path(p) / 'LibreOffice' / 'program' / exe for p in program_files if p]
    elif IS_MACOS:
        if name == 'soffice':
            candidates.append(Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'))
        elif name == 'tesseract':
            candidates += [Path('/opt/homebrew/bin/tesseract'), Path('/usr/local/bin/tesseract')]
        elif name == 'pdftoppm':
            candidates += [Path('/opt/homebrew/bin/pdftoppm'), Path('/usr/local/bin/pdftoppm')]
    else:
        candidates += [Path('/usr/bin') / name, Path('/usr/local/bin') / name, Path('/snap/bin') / name]
    return [c for c in candidates if c and str(c)]


def resolve_tool(name: str) -> str | None:
    """Find a program even when the installer did not add it to PATH (typical on Windows)."""
    found = shutil.which(name)
    if found:
        return found
    for candidate in _tool_candidates(name):
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def tool_status() -> dict:
    return {name: resolve_tool(name) is not None for name in ('tesseract', 'pdftoppm', 'soffice')}


def run_tool(command, timeout: int = 180) -> bytes:
    """Run an external converter/OCR tool without a flashing console window on Windows."""
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, timeout=timeout, check=False,
                                creationflags=_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError('LOCAL_TOOL_UNAVAILABLE') from None
    if result.returncode:
        raise ValueError('LOCAL_TOOL_FAILED')
    return result.stdout


def tesseract_languages() -> list[str]:
    exe = resolve_tool('tesseract')
    if not exe:
        return []
    try:
        result = subprocess.run([exe, '--list-langs'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, timeout=30, check=False, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return []
    text = result.stdout.decode('utf-8', 'replace')
    return [line.strip() for line in text.splitlines()[1:] if line.strip()]


# -------------------------------------------------------------------------- desktop

def open_folder(path) -> None:
    """Open the OS file manager; raise a stable error code instead of a raw exception."""
    target = Path(path)
    if IS_WINDOWS:
        try:
            os.startfile(str(target))  # type: ignore[attr-defined]
        except (OSError, AttributeError):
            raise ValueError('FOLDER_OPEN_FAILED') from None
        return
    opener = '/usr/bin/open' if IS_MACOS else shutil.which('xdg-open')
    if not opener:
        raise ValueError('FOLDER_OPEN_FAILED')
    try:
        result = subprocess.run([opener, str(target)], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        raise ValueError('FOLDER_OPEN_FAILED') from None
    if result.returncode:
        raise ValueError('FOLDER_OPEN_FAILED')


def reveal_folder(path) -> None:
    """Windows/Linux equivalent of Finder's "Reveal in Finder"; best effort."""
    target = Path(path)
    try:
        if IS_WINDOWS:
            subprocess.run(['explorer', '/select,' + str(target)], check=False,
                           creationflags=_NO_WINDOW)
        elif IS_MACOS:
            subprocess.run(['/usr/bin/open', '-R', str(target)], check=False)
        else:
            open_folder(target.parent)
    except (OSError, subprocess.SubprocessError):
        pass


# ---------------------------------------------------------------------------- clock

def shanghai_tz():
    """Windows ships no IANA database; zoneinfo needs the ``tzdata`` package."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo('Asia/Shanghai')
    except Exception:  # ZoneInfoNotFoundError, ModuleNotFoundError
        return timezone(timedelta(hours=8), 'Asia/Shanghai')


# ---------------------------------------------------------------------------- locks

class FileLock:
    """Non-blocking exclusive lock used for the single local workbench instance."""

    def __init__(self, path):
        self.path = Path(path)
        self.handle = None

    def acquire(self) -> bool:
        secure_dir(self.path.parent)
        handle = open(self.path, 'a+b')
        try:
            if IS_WINDOWS:
                import msvcrt
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, ImportError):
            handle.close()
            return False
        self.handle = handle
        secure_file(self.path)
        return True

    def release(self) -> None:
        handle = self.handle
        if handle is None:
            return
        self.handle = None
        try:
            if IS_WINDOWS:
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            handle.close()

    def __enter__(self):
        return self if self.acquire() else None

    def __exit__(self, *_exc):
        self.release()


# ------------------------------------------------------------------------- AI model

def model_status() -> dict:
    """Report whether local Chinese entity recognition can run, without loading it."""
    import importlib.util
    spacy_ok = importlib.util.find_spec('spacy') is not None
    package_ok = importlib.util.find_spec('zh_core_web_sm') is not None
    model_path = ''
    if not package_ok and spacy_ok:
        override = os.environ.get('LPC_SPACY_MODEL', '')
        if override and Path(override).exists():
            model_path = override
            package_ok = True
    return {'spacy': spacy_ok, 'model_package': package_ok, 'model_path': model_path}


def rule_only_requested() -> bool:
    """Explicit opt-in recorded by bootstrap when the Chinese model cannot be installed."""
    return os.environ.get('LPC_ALLOW_RULE_ONLY', '').strip().lower() in ('1', 'true', 'yes', 'on')
