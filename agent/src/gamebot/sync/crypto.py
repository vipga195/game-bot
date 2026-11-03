from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 200_000


def _key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(hashes.SHA256(), 32, salt, iterations)
    return kdf.derive(passphrase.encode())


def encrypt(passphrase: str, plaintext: str, iterations: int = ITERATIONS) -> dict:
    salt, nonce = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(passphrase, salt, iterations)).encrypt(nonce, plaintext.encode(), None)
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return {"salt": b64(salt), "nonce": b64(nonce), "ct": b64(ct), "iter": iterations}


def decrypt(passphrase: str, blob: dict) -> str:
    """Raises cryptography.exceptions.InvalidTag on a wrong passphrase or tampered data."""
    d = base64.b64decode
    key = _key(passphrase, d(blob["salt"]), blob["iter"])
    return AESGCM(key).decrypt(d(blob["nonce"]), d(blob["ct"]), None).decode()
