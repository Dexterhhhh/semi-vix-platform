"""Authenticated, secret-safe configuration for the active quote provider."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.config import get_settings
from app.data.credentials import encrypt_credential
from app.data.exceptions import ProviderError
from app.data.factory import create_provider
from app.database.database import get_db
from app.database.models import AdminAccount, AuditEvent, ProviderCredential

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provider", tags=["market-data provider"])


class CredentialInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    api_key: Optional[str] = Field(default=None, max_length=2048)
    secret: Optional[str] = Field(default=None, max_length=2048)
    account_identifier: Optional[str] = Field(default=None, max_length=2048)


class ProviderConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["IBKR", "FUTU"]
    credentials: CredentialInput = Field(default_factory=CredentialInput)


class ProviderStatusResponse(BaseModel):
    provider: Literal["IBKR", "FUTU"]
    configured: bool
    connected: bool
    last_checked_at: Optional[datetime] = None
    error: Optional[str] = None


class ProviderConfigurationResponse(BaseModel):
    provider: Literal["IBKR", "FUTU"]
    configured: bool
    host: str
    port: int
    client_id: Optional[int] = None
    credentials_present: bool


class ConfigureProviderResponse(BaseModel):
    provider: Literal["IBKR", "FUTU"]
    enabled: bool


def _active_credential(database: Session) -> ProviderCredential | None:
    return database.query(ProviderCredential).filter_by(enabled=True).first()


def _active_provider_name(database: Session) -> Literal["IBKR", "FUTU"]:
    credential = _active_credential(database)
    return credential.provider if credential else get_settings().data_provider


def _configuration_response(provider: Literal["IBKR", "FUTU"], credential: ProviderCredential | None) -> ProviderConfigurationResponse:
    settings = get_settings()
    if provider == "IBKR":
        return ProviderConfigurationResponse(provider=provider, configured=credential is not None, host=settings.ibkr_host, port=settings.ibkr_port, client_id=settings.ibkr_client_id, credentials_present=bool(credential and (credential.api_key_encrypted or credential.secret_encrypted or credential.account_identifier_encrypted)))
    return ProviderConfigurationResponse(provider=provider, configured=credential is not None, host=settings.futu_host, port=settings.futu_port, credentials_present=bool(credential and (credential.api_key_encrypted or credential.secret_encrypted or credential.account_identifier_encrypted)))


async def _check_connection(provider: Literal["IBKR", "FUTU"], configured: bool) -> ProviderStatusResponse:
    checked_at = datetime.now(timezone.utc)
    if not configured:
        return ProviderStatusResponse(provider=provider, configured=False, connected=False)
    instance = None
    try:
        instance = create_provider(provider)
        await asyncio.wait_for(instance.connect(), timeout=12)
        connected = await asyncio.wait_for(instance.health_check(), timeout=5)
        return ProviderStatusResponse(provider=provider, configured=True, connected=connected, last_checked_at=checked_at)
    except asyncio.TimeoutError:
        return ProviderStatusResponse(provider=provider, configured=True, connected=False, last_checked_at=checked_at, error="Provider connection timed out")
    except ProviderError:
        return ProviderStatusResponse(provider=provider, configured=True, connected=False, last_checked_at=checked_at, error="Provider unavailable")
    except Exception:
        logger.exception("Unexpected provider health-check failure for %s", provider)
        return ProviderStatusResponse(provider=provider, configured=True, connected=False, last_checked_at=checked_at, error="Provider health check failed")
    finally:
        if instance is not None:
            try:
                await asyncio.wait_for(instance.disconnect(), timeout=5)
            except Exception:
                logger.warning("Provider disconnect failed for %s", provider)


@router.get("/status", response_model=ProviderStatusResponse)
async def provider_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ProviderStatusResponse:
    credential = _active_credential(database)
    return await _check_connection(_active_provider_name(database), credential is not None)


@router.post("/configure", response_model=ConfigureProviderResponse)
async def configure_provider(payload: ProviderConfiguration, admin: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ConfigureProviderResponse:
    values = payload.credentials
    try:
        database.query(ProviderCredential).update({ProviderCredential.enabled: False})
        credential = database.query(ProviderCredential).filter_by(provider=payload.provider).first()
        if credential is None:
            credential = ProviderCredential(provider=payload.provider)
            database.add(credential)
        if values.api_key is not None:
            credential.api_key_encrypted = encrypt_credential(values.api_key)
        if values.secret is not None:
            credential.secret_encrypted = encrypt_credential(values.secret)
        if values.account_identifier is not None:
            credential.account_identifier_encrypted = encrypt_credential(values.account_identifier)
        credential.enabled = True
        database.add(AuditEvent(admin_id=admin.id, action="provider.configure", provider=payload.provider))
        database.commit()
    except Exception:
        database.rollback()
        raise
    return ConfigureProviderResponse(provider=payload.provider, enabled=True)


@router.post("/test-connection", response_model=ProviderStatusResponse)
async def test_provider_connection(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ProviderStatusResponse:
    credential = _active_credential(database)
    return await _check_connection(_active_provider_name(database), credential is not None)


@router.get("/configuration", response_model=ProviderConfigurationResponse)
async def provider_configuration(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ProviderConfigurationResponse:
    credential = _active_credential(database)
    return _configuration_response(_active_provider_name(database), credential)
