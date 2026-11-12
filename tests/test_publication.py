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
    monkeypatch.setattr(formats,'resolve_tool',lambda name:'synthetic-tesseract')
    monkeypatch.setattr(formats,'run',lambda cmd:raw)
    with pytest.raises(ValueError,match='^OCR_OUTPUT_INVALID$'):formats.ocr(b'synthetic-raster')
    formats._ocr.cache_clear()

def test_ocr_explicit_tsv_bom_and_no_config(monkeypatch):
    from cloak import formats
    calls=[];formats._ocr.cache_clear()
    raw='\ufefflevel\tpage_num\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n5\t1\t1\t1\t1\t10\t20\t30\t40\t95\tSynthetic\n'.encode('utf-8')
    monkeypatch.setattr(formats,'resolve_tool',lambda name:'synthetic-tesseract')
    monkeypatch.setattr(formats,'run',lambda cmd:calls.append(cmd) or raw)
    assert formats.ocr(b'synthetic-raster')[0].text=='Synthetic'
    assert calls[0][-2:]==['-c','tessedit_create_tsv=1'] and 'tsv' not in calls[0]
    formats._ocr.cache_clear()


def test_password_rejects_captured_stderr(monkeypatch):
    import lpc
    class FakeTTY:
        def isatty(self): return True
    class Captured:
        def isatty(self): return False
    monkeypatch.setattr(lpc.sys, 'stdin', FakeTTY())
    monkeypatch.setattr(lpc.sys, 'stderr', Captured())
    monkeypatch.setattr(lpc.getpass, 'getpass', lambda *args: pytest.fail('MUST_NOT_PROMPT'))
    with pytest.raises(ValueError, match='^LOCAL_TTY_REQUIRED$'):
        lpc.password()
