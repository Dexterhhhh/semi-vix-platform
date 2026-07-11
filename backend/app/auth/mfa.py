import json
import secrets
import pyotp
from app.auth.crypto import decrypt, encrypt


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Semi-VIX")


def verify_totp(encrypted_secret: str, code: str) -> bool:
    return pyotp.TOTP(decrypt(encrypted_secret)).verify(code, valid_window=1)


def encrypted_backup_codes() -> str:
    codes = [secrets.token_urlsafe(8).upper() for _ in range(8)]
    return encrypt(json.dumps(codes))
