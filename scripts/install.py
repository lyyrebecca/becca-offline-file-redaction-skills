#!/usr/bin/env python3
"""Explicit cross-platform installer; never touches source documents."""
import argparse,os,shutil,subprocess,sys,venv,json
from pathlib import Path
from cloak.platforms import data_home,runtime_python

def main():
    p=argparse.ArgumentParser();p.add_argument('--app',action='store_true');p.add_argument('--with-deps',action='store_true');p.add_argument('--target',type=Path,default=Path.home()/'.codex/skills/legal-privacy-cloak');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];target=a.target.expanduser().resolve()
    if sys.version_info<(3,11):raise SystemExit('Python 3.11+ required')
    if target.exists():raise SystemExit('Target exists; refuse to overwrite. Back up and remove it explicitly first.')
    runtime=data_home()/'venv';python=runtime_python()
    if a.with_deps:
        if not python.exists():venv.EnvBuilder(with_pip=True).create(runtime)
        subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
    if not python.exists():raise SystemExit('Runtime missing. Run installer with --with-deps.')
    result=subprocess.run([str(python),str(root/'scripts/lpc.py'),'doctor'],capture_output=True,text=True,encoding='utf-8',check=True)
    if json.loads(result.stdout)['status']!='READY':raise SystemExit('Dependencies incomplete; run doctor locally.')
    if a.app and sys.platform not in ('darwin','win32'):raise SystemExit('Desktop launcher supports macOS / Windows only.')
    app=Path.home()/'Applications/信息隐身衣.app'
    if a.app and sys.platform=='darwin' and app.exists():raise SystemExit('App exists; back it up explicitly before rebuilding.')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(root,target,ignore=shutil.ignore_patterns('.git','dist','.venv','__pycache__','.pytest_cache','*.pyc','.DS_Store'))
    if sys.platform!='win32':
        for n in ['scripts/run.sh','信息隐身衣.command']:os.chmod(target/n,0o755)
    if a.app and sys.platform=='darwin':
        from build_app import build
        app.parent.mkdir(exist_ok=True);build(app,target)
    if a.app and sys.platform=='win32':
        # A named Start Menu shortcut uses the supplied icon; no unsigned exe is fabricated.
        from PIL import Image
        icon=target/'assets/brand-icon.ico';Image.open(target/'assets/brand-icon.jpg').convert('RGBA').save(icon,format='ICO',sizes=[(32,32),(64,64),(128,128),(256,256)])
        shortcut=Path(os.environ['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/贝卡文件脱敏.lnk'
        shortcut.parent.mkdir(parents=True,exist_ok=True)
        if shortcut.exists():raise SystemExit('Shortcut exists; back it up explicitly first.')
        from cloak.windows_shortcut import create_shortcut
        create_shortcut(shortcut,python,'"'+str(target/'scripts/lpc.py')+'" desktop',target,icon)
    print('Installed legal-privacy-cloak. No other Agent configuration was changed.')
if __name__=='__main__':main()
