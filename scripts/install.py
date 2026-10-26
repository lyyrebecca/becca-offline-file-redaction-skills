#!/usr/bin/env python3
"""Explicit installer; no document processing or account/config changes."""
import argparse,os,shutil,subprocess,sys,venv
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--app',action='store_true');p.add_argument('--with-deps',action='store_true');p.add_argument('--target',type=Path,default=Path.home()/'.codex/skills/legal-privacy-cloak');a=p.parse_args()
    root=Path(__file__).resolve().parents[1];target=a.target.expanduser().resolve()
    if sys.version_info<(3,11):raise SystemExit('Python 3.11+ required')
    if target.exists():raise SystemExit('Target exists; refuse to overwrite. Back up and remove it explicitly first.')
    data=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'legal-privacy-cloak'
    runtime=data/'venv';python=runtime/'bin/python'
    if a.with_deps:
        if not python.exists():venv.EnvBuilder(with_pip=True).create(runtime)
        subprocess.run([str(python),'-m','pip','install','-r',str(root/'requirements.txt')],check=True)
    if not python.exists():raise SystemExit('Runtime missing. Run installer with --with-deps.')
    result=subprocess.run([str(python),str(root/'scripts/lpc.py'),'doctor'],capture_output=True,text=True,check=True)
    import json
    if json.loads(result.stdout)['status']!='READY':raise SystemExit('Dependencies incomplete; run doctor locally.')
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(root,target,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache','*.pyc','.DS_Store'))
    for n in ['scripts/run.sh','信息隐身衣.command']:os.chmod(target/n,0o755)
    if a.app:
        from build_app import build
        folder=Path.home()/'Applications';folder.mkdir(exist_ok=True)
        app=folder/'信息隐身衣.app'
        if app.exists():raise SystemExit('App exists; back it up explicitly before rebuilding.')
        build(app,target)
    print('Installed legal-privacy-cloak. No other Agent configuration was changed.')
if __name__=='__main__':main()
