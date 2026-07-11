import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import get_settings


def _key() -> bytes:
    key = base64.urlsafe_b64decode(get_settings().credential_master_key.get_secret_value().encode())
    if len(key) != 32:
        raise ValueError("CREDENTIAL_MASTER_KEY must decode to exactly 32 bytes")
    return key


def encrypt_credential(value: str) -> str:
    nonce = os.urandom(12)
    return base64.urlsafe_b64encode(nonce + AESGCM(_key()).encrypt(nonce, value.encode(), None)).decode()


def decrypt_credential(value: str) -> str:
    payload = base64.urlsafe_b64decode(value.encode())
    return AESGCM(_key()).decrypt(payload[:12], payload[12:], None).decode()
