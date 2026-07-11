from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AdminAccount, SessionRecord

bearer_scheme = HTTPBearer(auto_error=False)


def _encode(payload: dict) -> str:
    return jwt.encode(payload, get_settings().secret_key.get_secret_value(), algorithm="HS256")


def create_temporary_token(admin: AdminAccount, purpose: str) -> str:
    return _encode({"sub": str(admin.id), "type": "temporary", "purpose": purpose, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)})


def create_access_token(admin: AdminAccount) -> str:
    return _encode({"sub": str(admin.id), "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=get_settings().jwt_expire_minutes)})


def validate_temporary_token(token: str, purpose: str) -> int:
    try:
        payload = jwt.decode(token, get_settings().secret_key.get_secret_value(), algorithms=["HS256"])
        if payload.get("type") != "temporary" or payload.get("purpose") != purpose:
            raise ValueError("wrong token type")
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired temporary token") from exc


def create_refresh_token(database: Session, ip_address: Optional[str]) -> str:
    raw = secrets.token_urlsafe(48)
    database.add(SessionRecord(refresh_token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(timezone.utc) + timedelta(days=get_settings().refresh_expire_days), ip_address=ip_address))
    return raw


def get_current_admin(credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme), database: Session = Depends(get_db)) -> AdminAccount:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, get_settings().secret_key.get_secret_value(), algorithms=["HS256"])
        if payload.get("type") != "access":
            raise ValueError("wrong token type")
        admin = database.get(AdminAccount, int(payload["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired access token") from exc
    if admin is None or not admin.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account unavailable")
    return admin
