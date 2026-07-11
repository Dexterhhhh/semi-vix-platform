from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.auth.crypto import encrypt
from app.auth.jwt import create_access_token, create_refresh_token, create_temporary_token, get_current_admin, validate_temporary_token
from app.auth.mfa import encrypted_backup_codes, generate_totp_secret, provisioning_uri, verify_totp
from app.auth.password import verify_password
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AdminAccount, AdminSecurity

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=512)


class SetupMFARequest(BaseModel):
    temporary_token: str = Field(min_length=20)
    totp_code: Optional[str] = Field(default=None, min_length=6, max_length=6)


class VerifyMFARequest(BaseModel):
    temporary_token: str = Field(min_length=20)
    totp_code: str = Field(min_length=6, max_length=6)


def _token_response(response: Response, database: Session, admin: AdminAccount, request: Request) -> dict[str, Any]:
    settings = get_settings()
    refresh = create_refresh_token(database, request.client.host if request.client else None)
    database.commit()
    response.set_cookie("svix_refresh", refresh, httponly=True, secure=settings.cookie_secure, samesite="strict", max_age=settings.refresh_expire_days * 86400, path="/api/auth")
    return {"access_token": create_access_token(admin), "token_type": "bearer", "expires_in": settings.jwt_expire_minutes * 60}


@router.post("/login")
async def login(payload: LoginRequest, database: Session = Depends(get_db)) -> dict[str, Any]:
    admin = database.query(AdminAccount).filter_by(username=payload.username).first()
    if admin is None or not admin.is_active or not verify_password(payload.password, admin.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    security = database.query(AdminSecurity).filter_by(admin_id=admin.id).one()
    if security.mfa_enabled:
        return {"mfa_required": True, "temporary_token": create_temporary_token(admin, "verify")}
    return {"mfa_setup_required": True, "temporary_token": create_temporary_token(admin, "setup")}


@router.post("/setup-mfa")
async def setup_mfa(payload: SetupMFARequest, response: Response, request: Request, database: Session = Depends(get_db)) -> dict:
    admin = database.get(AdminAccount, validate_temporary_token(payload.temporary_token, "setup"))
    security = database.query(AdminSecurity).filter_by(admin_id=admin.id).one()
    if security.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA already enabled")
    if payload.totp_code is None:
        secret = generate_totp_secret()
        security.totp_secret_encrypted = encrypt(secret)
        database.commit()
        return {"provisioning_uri": provisioning_uri(secret, admin.username), "verification_required": True}
    if not security.totp_secret_encrypted or not verify_totp(security.totp_secret_encrypted, payload.totp_code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid TOTP code")
    security.mfa_enabled = True
    security.backup_codes_encrypted = encrypted_backup_codes()
    admin.last_login = datetime.now(timezone.utc)
    return _token_response(response, database, admin, request)


@router.post("/verify-mfa")
async def verify_mfa(payload: VerifyMFARequest, response: Response, request: Request, database: Session = Depends(get_db)) -> dict[str, Any]:
    admin = database.get(AdminAccount, validate_temporary_token(payload.temporary_token, "verify"))
    security = database.query(AdminSecurity).filter_by(admin_id=admin.id).one()
    if not security.mfa_enabled or not security.totp_secret_encrypted or not verify_totp(security.totp_secret_encrypted, payload.totp_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid TOTP code")
    admin.last_login = datetime.now(timezone.utc)
    return _token_response(response, database, admin, request)


@router.get("/me")
async def me(admin: AdminAccount = Depends(get_current_admin)) -> dict[str, str]:
    return {"username": admin.username}
