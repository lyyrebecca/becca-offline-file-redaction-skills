from __future__ import annotations
import base64, json, os
from pathlib import Path
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .platform_support import atomic_write, read_bytes
MAGIC=b'LPCV1\x00';AAD=b'legal-privacy-cloak/v1'

def derive(password,salt):
    if not isinstance(password,str) or len(password)<12:raise ValueError('PASSPHRASE_MIN_12')
    return Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(password.encode())

def atomic(path,data):
    # fchmod is POSIX-only; atomic_write centralises POSIX permissions, Windows
    # replacement semantics and long paths so the vault can be written on every OS.
    atomic_write(path,data)

def seal(path,obj,password):
    salt=os.urandom(16);nonce=os.urandom(12)
    raw=json.dumps(obj,ensure_ascii=False,separators=(',',':')).encode()
    ciphertext=AESGCM(derive(password,salt)).encrypt(nonce,raw,AAD)
    atomic(path,MAGIC+salt+nonce+ciphertext)

def open_vault(path,password):
    raw=read_bytes(path)
    if len(raw)<50 or raw[:len(MAGIC)]!=MAGIC:raise ValueError('VAULT_INVALID')
    off=len(MAGIC);salt=raw[off:off+16];nonce=raw[off+16:off+28]
    return json.loads(AESGCM(derive(password,salt)).decrypt(nonce,raw[off+28:],AAD))

def b64(data):return base64.b64encode(data).decode('ascii')
def unb64(s):return base64.b64decode(s,validate=True)
