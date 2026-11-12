"""Portable, versioned per-user runtime paths for the standalone skill folder."""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

VERSION = "2.4.2"
CONFIG_NAME = "runtime.json"


def runtime_home() -> Path:
    override = os.environ.get("LPC_RUNTIME_HOME")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "legal-privacy-cloak" / VERSION
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "legal-privacy-cloak" / VERSION
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "legal-privacy-cloak" / VERSION


def runtime_python() -> Path:
    root = runtime_home() / "venv"
    if sys.platform == "win32":
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def runtime_scripts() -> Path:
    root = runtime_home() / "venv"
    return root / "Scripts" if sys.platform == "win32" else root / "bin"


def config_path() -> Path:
    return runtime_home() / CONFIG_NAME


def read_config() -> dict:
    try:
        value = json.loads(config_path().read_text("utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(values: dict) -> None:
    home = runtime_home()
    home.mkdir(parents=True, exist_ok=True)
    merged = {**read_config(), **values}
    target = config_path()
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
    os.replace(temporary, target)


def allow_rule_only() -> bool:
    """True when the user explicitly accepted rule-only detection (no Chinese model)."""
    if os.environ.get("LPC_ALLOW_RULE_ONLY", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return read_config().get("allow_rule_only") is True
