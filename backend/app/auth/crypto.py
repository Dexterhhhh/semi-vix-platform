import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import get_settings


def _key() -> bytes:
    key = base64.urlsafe_b64decode(get_settings().secret_encryption_key.get_secret_value().encode())
    if len(key) != 32:
        raise ValueError("SECRET_ENCRYPTION_KEY must decode to 32 bytes")
    return key


def encrypt(value: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key()).encrypt(nonce, value.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(value: str) -> str:
    payload = base64.urlsafe_b64decode(value.encode())
    return AESGCM(_key()).decrypt(payload[:12], payload[12:], None).decode()
