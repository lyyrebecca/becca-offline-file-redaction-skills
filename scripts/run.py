#!/usr/bin/env python3
"""Dispatch commands to the versioned per-user runtime for this skill."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

if not (3, 11) <= sys.version_info < (3, 13):
    print("本 Skill 需要 Python 3.11 或 3.12；当前解释器版本为 %s。" % sys.version.split()[0], file=sys.stderr)
    print("Windows 请安装 python.org 的 3.12 并勾选 Add python.exe to PATH；macOS 可用 python.org 安装包或 brew install python@3.12。", file=sys.stderr)
    raise SystemExit(2)

from runtime import runtime_python

root = Path(__file__).resolve().parents[1]
python = runtime_python()

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

if not python.is_file():
    print("本机尚未安装此 Skill 的 Python 环境。首次使用请在本机运行：", file=sys.stderr)
    if os.name == "nt":
        print(f'  py -3.12 "{root / "scripts" / "bootstrap.py"}"', file=sys.stderr)
    else:
        print(f'  python3.12 "{root / "scripts" / "bootstrap.py"}"', file=sys.stderr)
    raise SystemExit(2)

command = [str(python), str(root / "scripts" / "lpc.py"), *sys.argv[1:]]
if os.name == "nt":
    # os.execv on Windows re-launches through the CRT and can detach the console handle;
    # a child process keeps Ctrl+C, exit codes and window behaviour predictable.
    completed = subprocess.run(command)
    raise SystemExit(completed.returncode)
os.execv(str(python), command)
