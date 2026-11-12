#!/usr/bin/env python3
"""Optional installer: local runtime, copy into an Agent folder, and native launchers."""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from runtime import runtime_python
from cloak import platform_support as ps


def doctor(python: Path, root: Path) -> dict | None:
    try:
        check = subprocess.run([str(python), str(root / "scripts" / "lpc.py"), "doctor"],
                               capture_output=True, text=True, check=False,
                               encoding="utf-8", errors="replace")
        return json.loads(check.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None


def windows_shortcut(skill: Path, python: Path, where: str) -> Path:
    """Create a .lnk without admin rights; pythonw keeps the local server console-free."""
    pythonw = python.with_name("pythonw.exe")
    target = pythonw if pythonw.is_file() else python
    icon = skill / "assets" / "icon.ico"
    folder = ps.desktop_dir() if where == "desktop" else (
        Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    folder.mkdir(parents=True, exist_ok=True)
    link = folder / "信息隐身衣.lnk"
    script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        f"$s = $ws.CreateShortcut('{str(link).replace(chr(39), chr(39) * 2)}');"
        f"$s.TargetPath = '{str(target).replace(chr(39), chr(39) * 2)}';"
        f"$s.Arguments = '\"{str((skill / 'scripts' / 'lpc.py')).replace(chr(39), chr(39) * 2)}\" desktop';"
        f"$s.WorkingDirectory = '{str(skill).replace(chr(39), chr(39) * 2)}';"
        f"$s.IconLocation = '{str(icon).replace(chr(39), chr(39) * 2)}';"
        "$s.WindowStyle = 7;$s.Description = '信息隐身衣 · 本地法律材料工作台';$s.Save()"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                            capture_output=True, text=True, check=False,
                            encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode or not link.exists():
        raise ValueError("SHORTCUT_FAILED")
    return link


def linux_shortcut(skill: Path) -> Path:
    applications = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "applications"
    applications.mkdir(parents=True, exist_ok=True)
    entry = applications / "legal-privacy-cloak.desktop"
    entry.write_text(
        "[Desktop Entry]\nType=Application\nName=信息隐身衣\n"
        "Comment=本地法律材料去标识化与加密恢复\n"
        f"Exec=\"{skill / 'scripts' / 'run.sh'}\" desktop\nPath={skill}\n"
        f"Icon={skill / 'assets' / 'icon-256.png'}\nTerminal=false\nCategories=Office;Utility;\n",
        "utf-8")
    try:
        entry.chmod(0o755)
    except OSError:
        pass
    return entry


def main() -> int:
    ps.configure_stdio()
    parser = argparse.ArgumentParser(description="安装当前 Skill 的本机运行环境；不会处理文件内容")
    parser.add_argument("--with-deps", action="store_true", help="按 requirements.txt 新建/更新本机 Python 环境")
    parser.add_argument("--target", type=Path, help="可选：将当前 Skill 复制到指定 Agent skills 目录")
    parser.add_argument("--app", action="store_true", help="仅 macOS：在 ~/Applications 创建 .app")
    parser.add_argument("--shortcut", choices=["desktop", "startmenu"], help="Windows/Linux：创建桌面或开始菜单快捷方式")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = runtime_python()

    if args.with_deps:
        result = subprocess.run([sys.executable, str(root / "scripts" / "bootstrap.py")], check=False)
        if result.returncode:
            return result.returncode
    if not python.is_file():
        print("本机运行环境不存在。请先运行 scripts/bootstrap.py（首次安装需访问 Python 包源）。", file=sys.stderr)
        return 2

    state = doctor(python, root)
    if not state or state.get("status") != "READY":
        print("Python 依赖或中文模型尚未就绪；请重新运行 scripts/bootstrap.py。", file=sys.stderr)
        if state:
            for warning in state.get("warnings", []):
                print("  " + warning, file=sys.stderr)
        return 1

    installed_root = root
    if args.target:
        target = args.target.expanduser().resolve()
        if target != root:
            if target.exists():
                print("目标目录已存在；为避免覆盖，请备份并手动指定一个空目录。", file=sys.stderr)
                return 2
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(root, target, ignore=shutil.ignore_patterns(
                "__pycache__", ".pytest_cache", "*.pyc", ".DS_Store", ".git"))
            installed_root = target
        if os.name != "nt":
            for relative in ("scripts/run.sh", "信息隐身衣.command"):
                path = installed_root / relative
                if path.exists():
                    try:
                        path.chmod(0o755)
                    except OSError:
                        pass

    if args.app:
        if sys.platform != "darwin":
            print(".app 启动器仅支持 macOS；Windows 请使用 --shortcut desktop，或直接双击 信息隐身衣.cmd。", file=sys.stderr)
            return 2
        app = Path.home() / "Applications" / "信息隐身衣.app"
        if app.exists():
            print("应用已存在；为避免覆盖，请先将旧应用备份或移走。", file=sys.stderr)
            return 2
        result = subprocess.run([str(python), str(root / "scripts" / "build_app.py"),
                                 "--target", str(app), "--skill", str(installed_root)], check=False)
        if result.returncode:
            return result.returncode

    if args.shortcut:
        try:
            if os.name == "nt":
                link = windows_shortcut(installed_root, python, args.shortcut)
            elif sys.platform == "darwin":
                print("macOS 请使用 --app 创建启动器。", file=sys.stderr)
                return 2
            else:
                if args.shortcut != "desktop":
                    print("Linux 仅创建应用菜单项。", file=sys.stderr)
                link = linux_shortcut(installed_root)
        except (OSError, ValueError) as exc:
            print(f"快捷方式创建失败（{type(exc).__name__}）。可直接双击 信息隐身衣.cmd 或运行 scripts\\run.cmd desktop。", file=sys.stderr)
            return 1
        print(f"快捷方式：{link}")

    print("当前 Skill 的本机 Python 环境已就绪。")
    print(f"平台：{state.get('platform')} · 中文实体识别：{state.get('ner')} · OCR：{state.get('ocr_status')}")
    for warning in state.get("warnings", []):
        print("提示：" + warning)
    if args.target and installed_root != root:
        print(f"Skill 目录：{installed_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
