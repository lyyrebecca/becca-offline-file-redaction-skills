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
