#!/usr/bin/env python3
"""Create a minimal macOS launcher for the fixed local engine; no web hosting or accounts."""
from pathlib import Path
import argparse,plistlib,shutil
from PIL import Image

def build(target,skill):
    target=Path(target).expanduser().resolve();skill=Path(skill).resolve()
    if target.exists():raise ValueError('APP_TARGET_EXISTS')
    mac=target/'Contents/MacOS';resources=target/'Contents/Resources';mac.mkdir(parents=True);resources.mkdir()
    Image.open(skill/'assets/brand-icon.jpg').convert('RGBA').resize((1024,1024)).save(resources/'Icon.icns')
    # quote user-controlled installation path as a literal shell argument
    import shlex
    launch='#!/bin/sh\nexport PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"\nexec '+shlex.quote(str(skill/'scripts/run.sh'))+' desktop </dev/null >/dev/null 2>&1 &\nexit 0\n'
    exe=mac/'launch';exe.write_text(launch);exe.chmod(0o755)
    info={'CFBundleName':'信息隐身衣','CFBundleDisplayName':'信息隐身衣','CFBundleIdentifier':'com.lyyrebecca.legal-privacy-cloak','CFBundleVersion':'2.0.1','CFBundleShortVersionString':'2.0.1','CFBundleExecutable':'launch','CFBundleIconFile':'Icon.icns','CFBundlePackageType':'APPL','LSUIElement':True,'NSHighResolutionCapable':True}
    (target/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    return target
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--target',type=Path,required=True);p.add_argument('--skill',type=Path,default=Path(__file__).resolve().parents[1]);a=p.parse_args();print(build(a.target,a.skill))
