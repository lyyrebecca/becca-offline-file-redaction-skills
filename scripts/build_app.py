#!/usr/bin/env python3
"""Create a minimal macOS launcher for the fixed local engine; no web hosting or accounts."""
from __future__ import annotations
import argparse, plistlib, shlex, sys
from pathlib import Path
from PIL import Image
from runtime import VERSION

LOG_NAME = '信息隐身衣.log'


def _icon(skill: Path, resources: Path) -> str | None:
    """Write an .icns bundle icon; fall back to no icon rather than failing the build."""
    source = skill / 'assets' / 'icon-256.png'
    if not source.is_file():
        source = skill / 'assets' / 'brand-icon.jpg'
    if not source.is_file():
        return None
    try:
        with Image.open(source) as image:
            image.convert('RGBA').resize((1024, 1024), Image.LANCZOS).save(resources / 'Icon.icns')
    except (OSError, ValueError):
        return None
    return 'Icon.icns'


def build(target, skill):
    target = Path(target).expanduser().resolve()
    skill = Path(skill).resolve()
    if target.exists():
        raise ValueError('APP_TARGET_EXISTS')
    mac = target / 'Contents' / 'MacOS'
    resources = target / 'Contents' / 'Resources'
    mac.mkdir(parents=True)
    resources.mkdir()
    icon = _icon(skill, resources)
    # The launcher keeps a log: a GUI app started by Finder has no terminal to show errors in.
    launch = ('#!/bin/sh\n'
              'export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\n'
              f'LOG="$HOME/Library/Logs/{LOG_NAME}"\n'
              'mkdir -p "$HOME/Library/Logs"\n'
              f'exec {shlex.quote(str(skill / "scripts" / "run.sh"))} desktop '
              '>>"$LOG" 2>&1 </dev/null &\n'
              'exit 0\n')
    executable = mac / 'launch'
    executable.write_text(launch, 'utf-8')
    executable.chmod(0o755)
    (target / 'Contents' / 'PkgInfo').write_bytes(b'APPL????')
    info = {'CFBundleName': '信息隐身衣', 'CFBundleDisplayName': '信息隐身衣',
            'CFBundleIdentifier': 'org.infocloak.legal-privacy-cloak',
            'CFBundleVersion': VERSION, 'CFBundleShortVersionString': VERSION,
            'CFBundleExecutable': 'launch', 'CFBundlePackageType': 'APPL',
            'CFBundleInfoDictionaryVersion': '6.0',
            'LSMinimumSystemVersion': '11.0', 'LSUIElement': True, 'NSHighResolutionCapable': True}
    if icon:
        info['CFBundleIconFile'] = icon
    (target / 'Contents' / 'Info.plist').write_bytes(plistlib.dumps(info))
    return target


if __name__ == '__main__':
    if sys.platform != 'darwin':
        raise SystemExit('仅 macOS 使用 .app 启动器；Windows 请使用 信息隐身衣.cmd 或 scripts\\run.cmd desktop。')
    parser = argparse.ArgumentParser(description='为本机固定引擎创建 macOS 启动应用')
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--skill', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(build(args.target, args.skill))
