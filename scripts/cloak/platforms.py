"""Platform integration only. No network calls or shell-interpolated paths."""
import os,sys,shutil,subprocess
from pathlib import Path

def data_home():
    if sys.platform=='win32':return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'legal-privacy-cloak'
    return Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'legal-privacy-cloak'

def runtime_python():
    return data_home()/'venv'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')

def prepare_tools():
    if sys.platform!='win32':return
    roots=[Path(os.environ.get('ProgramFiles','C:/Program Files')),Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))]
    candidates=[p for root in roots for p in (root/'Tesseract-OCR',root/'Programs/Tesseract-OCR')]
    candidates += list(Path(os.environ.get('ChocolateyInstall','C:/ProgramData/chocolatey')).glob('lib/poppler*/tools/**/bin'))
    os.environ['PATH']=os.pathsep.join(str(p) for p in candidates if p.is_dir())+os.pathsep+os.environ.get('PATH','')

def open_folder(path):
    target=Path(path).resolve()
    if not target.is_dir():raise ValueError('OUTPUT_NOT_FOUND')
    try:
        if sys.platform=='win32':os.startfile(str(target));return
        cmd=['/usr/bin/open' if sys.platform=='darwin' else 'xdg-open',str(target)]
        if subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8).returncode:raise ValueError('FOLDER_OPEN_FAILED')
    except (OSError,subprocess.TimeoutExpired):raise ValueError('FOLDER_OPEN_FAILED') from None

def libreoffice():
    found=shutil.which('soffice')
    if found:return Path(found)
    candidates=[Path('/Applications/LibreOffice.app/Contents/MacOS/soffice')]
    if sys.platform=='win32':candidates=[Path(os.environ.get('ProgramFiles','C:/Program Files'))/'LibreOffice/program/soffice.exe']
    return next((p for p in candidates if p.is_file()),None)

def lock_file(handle,unlock=False):
    if sys.platform=='win32':
        import msvcrt,time
        handle.seek(0)
        if unlock:msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1);return
        deadline=time.monotonic()+30
        while True:
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1);return
            except OSError:
                if time.monotonic()>=deadline:raise ValueError('LAUNCH_BUSY') from None
                time.sleep(.1)
    else:
        import fcntl
        fcntl.flock(handle,fcntl.LOCK_UN if unlock else fcntl.LOCK_EX)
