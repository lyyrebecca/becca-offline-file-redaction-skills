#!/usr/bin/env python3
"""Build a source Skill archive from an explicit public-file allowlist, never task data."""
from __future__ import annotations
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'SKILL.md', 'README.md', 'README.en.md', '开始使用.md', 'CHANGELOG.md',
    'LICENSE', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md', '发行验收报告.md',
    'requirements.txt', 'requirements-model.txt', 'requirements-test.txt',
    'requirements-tested.txt', '信息隐身衣.cmd', '信息隐身衣.command', '.gitattributes',
)
DIRECTORIES = ('agents', 'assets', 'references', 'scripts', 'tests', 'docs')
SUFFIXES = {'.py', '.js', '.css', '.html', '.md', '.yaml', '.yml', '.json', '.txt',
            '.jpg', '.jpeg', '.png', '.ico', '.icns', '.sh', '.cmd', '.ps1', '.command'}


def payload():
    paths = [ROOT / name for name in FILES]
    for directory in DIRECTORIES:
        paths.extend(p for p in (ROOT / directory).rglob('*')
                     if p.is_file() and p.suffix.lower() in SUFFIXES
                     and not any(part.startswith('.') or part == '__pycache__'
                                 for part in p.relative_to(ROOT / directory).parts))
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError('UNSAFE_RELEASE_PATH')
        if not path.is_file():
            raise ValueError('MISSING_RELEASE_FILE:' + path.name)
        yield path


def main():
    parser = argparse.ArgumentParser(description='Build the public source Skill ZIP only')
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    version = json.loads((ROOT / 'assets/brand.json').read_text('utf-8'))['version']
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    archive = out / f'legal-privacy-cloak-{version}.zip'
    paths = list(payload())
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in paths:
            name = 'legal-privacy-cloak/' + path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            info.create_system = 3
            mode = 0o100755 if name.endswith(('.sh', '.command')) else 0o100644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (out / 'SHA256SUMS.txt').write_text(f'{checksum}  {archive.name}\n', 'utf-8')
    print(json.dumps({'archive': str(archive), 'files': len(paths), 'sha256': checksum}, indent=2))


if __name__ == '__main__':
    main()
