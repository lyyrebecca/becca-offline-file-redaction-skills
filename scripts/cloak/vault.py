from __future__ import annotations
import base64, json, os, struct, tempfile
from pathlib import Path
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
MAGIC=b'LPCV1\x00';AAD=b'legal-privacy-cloak/v1'

def derive(password,salt):
    if not isinstance(password,str) or len(password)<12:raise ValueError('PASSPHRASE_MIN_12')
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode())

def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,tmp=tempfile.mkstemp(prefix='.lpc-',dir=path.parent)
    try:
        if os.name!='nt':os.fchmod(fd,0o600)
        # Windows uses the user-profile ACL; POSIX mode bits are not an ACL guarantee.
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def seal(path,obj,password):
    salt=os.urandom(16);nonce=os.urandom(12)
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode()
    ciphertext=AESGCM(derive(password,salt)).encrypt(nonce,raw,AAD)
    atomic(path,MAGIC+salt+nonce+ciphertext)

def open_vault(path,password):
    raw=Path(path).read_bytes()
    if len(raw)<50 or raw[:len(MAGIC)]!=MAGIC:raise ValueError('VAULT_INVALID')
    off=len(MAGIC);salt=raw[off:off+16];nonce=raw[off+16:off+28]
    return json.loads(AESGCM(derive(password,salt)).decrypt(nonce,raw[off+28:],AAD))

def b64(data):return base64.b64encode(data).decode('ascii')
def unb64(s):return base64.b64decode(s,validate=True)
