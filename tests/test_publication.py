"""Clean-environment publication regression; all test content is synthetic."""
import socket
from http.server import BaseHTTPRequestHandler
from cloak.localhttp import LocalHTTPServer,LocalThreadingHTTPServer
import pytest

@pytest.mark.parametrize('server_type',[LocalHTTPServer,LocalThreadingHTTPServer])
def test_loopback_startup_never_resolves_dns(monkeypatch,server_type):
    def no_dns(*args):raise AssertionError('REVERSE_DNS_FORBIDDEN')
    monkeypatch.setattr(socket,'getfqdn',no_dns)
    with server_type(('127.0.0.1',0),BaseHTTPRequestHandler) as server:
        assert server.server_name=='127.0.0.1' and server.server_port>0

@pytest.mark.parametrize('raw',[b'Phone: synthetic\n',b'',b'level\ttext\n5\tHello\n'])
def test_non_tsv_ocr_is_blocked(monkeypatch,raw):
    from cloak import formats
    formats._ocr.cache_clear()
    monkeypatch.setattr(formats,'run',lambda cmd:raw)
    with pytest.raises(ValueError,match='^OCR_OUTPUT_INVALID$'):formats.ocr(b'synthetic-raster')
    formats._ocr.cache_clear()

def test_ocr_explicit_tsv_bom_and_no_config(monkeypatch):
    from cloak import formats
    calls=[];formats._ocr.cache_clear()
    raw='\ufefflevel\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t10\t20\t30\t40\t95\tSynthetic\n'.encode('utf-8')
    monkeypatch.setattr(formats,'run',lambda cmd:calls.append(cmd) or raw)
    assert formats.ocr(b'synthetic-raster')[0].text=='Synthetic'
    assert calls[0][-2:]==['-c','tessedit_create_tsv=1'] and 'tsv' not in calls[0]
    formats._ocr.cache_clear()

def test_platform_runtime_path(monkeypatch,tmp_path):
    from cloak import platforms
    monkeypatch.setattr(platforms.sys,'platform','win32');monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    assert platforms.runtime_python()==tmp_path/'legal-privacy-cloak/venv/Scripts/python.exe'

def test_native_folder_open_windows(monkeypatch,tmp_path):
    from cloak import platforms
    calls=[];monkeypatch.setattr(platforms.sys,'platform','win32')
    monkeypatch.setattr(platforms.os,'startfile',lambda path:calls.append(path),raising=False)
    platforms.open_folder(tmp_path)
    assert calls==[str(tmp_path.resolve())]

def test_native_process_lock(tmp_path):
    from cloak.platforms import lock_file
    with (tmp_path/'lock').open('a+b') as f:
        lock_file(f);lock_file(f,unlock=True)

def test_installer_and_native_launcher_from_unicode_path(tmp_path,monkeypatch):
    """Real subprocess, fresh isolated install; reuse already installed dependency packages."""
    import json,os,subprocess,sys,venv
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    env=os.environ.copy();env['PYTHONUTF8']='1'
    data=tmp_path/'本地运行环境 with spaces';env['LOCALAPPDATA']=str(data);env['XDG_DATA_HOME']=str(data)
    runtime=data/'legal-privacy-cloak/venv';venv.EnvBuilder(system_site_packages=True).create(runtime)
    python=runtime/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    import site,sysconfig
    packages=Path(sysconfig.get_path('purelib',vars={'base':str(runtime),'platbase':str(runtime)}));packages.mkdir(parents=True,exist_ok=True)
    (packages/'synthetic-test-dependencies.pth').write_text('\n'.join(site.getsitepackages())+'\n',encoding='utf-8')
    target=tmp_path/'中文安装目录 with spaces'/'legal-privacy-cloak'
    command=[sys.executable,str(root/'scripts/install.py'),'--target',str(target)]
    if sys.platform=='win32':
        env['APPDATA']=str(tmp_path/'StartMenu测试');command.append('--app')
    result=subprocess.run(command,env=env,capture_output=True,timeout=90)
    assert result.returncode==0,result.stderr.decode('utf-8','replace')
    assert (target/'SKILL.md').is_file() and not (target/'.git').exists()
    if sys.platform=='win32':
        assert (Path(env['APPDATA'])/'Microsoft/Windows/Start Menu/Programs/贝卡文件脱敏.lnk').is_file()
        launcher=['cmd.exe','/d','/c',str(target/'scripts/run.cmd'),'doctor']
    else:launcher=['sh',str(target/'scripts/run.sh'),'doctor']
    result=subprocess.run(launcher,env=env,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr.decode('utf-8','replace')
    assert json.loads(result.stdout.decode('utf-8'))['status']=='READY'

def test_release_zip_uses_portable_paths_and_matches_manifest(tmp_path):
    import hashlib,json,zipfile
    from build_release import build
    build(tmp_path)
    manifest=json.loads((tmp_path/'release-manifest.json').read_text('utf-8'))
    archive=next(tmp_path.glob('*.zip'))
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert all('\\' not in name and name.startswith('legal-privacy-cloak/') for name in z.namelist())
        assert len(z.namelist())==len(manifest['files'])
        for name,digest in manifest['files'].items():
            assert hashlib.sha256(z.read('legal-privacy-cloak/'+name)).hexdigest()==digest
        assert not any(name.endswith('.lpcv') or '/.git/' in name or '/private/' in name for name in z.namelist())
