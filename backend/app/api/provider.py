"""Authenticated, secret-safe configuration for the active quote provider."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.config import get_settings
from app.data.credentials import decrypt_credential, encrypt_credential
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

    provider: Literal["IBKR", "FUTU", "ALPACA"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    client_id: Optional[int] = Field(default=None, ge=0, le=2147483647)
    data_feed: Optional[Literal["indicative", "opra"]] = None
    credentials: CredentialInput = Field(default_factory=CredentialInput)


class ProviderStatusResponse(BaseModel):
    provider: Literal["IBKR", "FUTU", "ALPACA"]
    configured: bool
    connected: bool
    last_checked_at: Optional[datetime] = None
    error: Optional[str] = None
    data_feed: Optional[Literal["indicative", "opra"]] = None
    production_ready: bool = True
    warning: Optional[str] = None


class ProviderConfigurationResponse(BaseModel):
    provider: Literal["IBKR", "FUTU", "ALPACA"]
    configured: bool
    host: str
    port: int
    client_id: Optional[int] = None
    credentials_present: bool
    data_feed: Optional[Literal["indicative", "opra"]] = None
    production_ready: bool = True
    warning: Optional[str] = None


class ConfigureProviderResponse(BaseModel):
    provider: Literal["IBKR", "FUTU", "ALPACA"]
    enabled: bool


def _active_credential(database: Session) -> ProviderCredential | None:
    return database.query(ProviderCredential).filter_by(enabled=True).first()


def _active_provider_name(database: Session) -> Literal["IBKR", "FUTU", "ALPACA"]:
    credential = _active_credential(database)
    return credential.provider if credential else get_settings().data_provider


def _alpaca_warning(feed: str | None) -> str | None:
    if feed == "indicative":
        return "Alpaca 免费 indicative 报价经过修改；可用于 SVIX，但结果会标记较低数据质量。"
    return None


def _configuration_response(provider: Literal["IBKR", "FUTU", "ALPACA"], credential: ProviderCredential | None) -> ProviderConfigurationResponse:
    settings = get_settings()
    if provider == "IBKR":
        return ProviderConfigurationResponse(provider=provider, configured=credential is not None, host=credential.host if credential and credential.host else settings.ibkr_host, port=credential.port if credential and credential.port else settings.ibkr_port, client_id=credential.client_id if credential and credential.client_id is not None else settings.ibkr_client_id, credentials_present=bool(credential and (credential.api_key_encrypted or credential.secret_encrypted or credential.account_identifier_encrypted)))
    if provider == "FUTU":
        return ProviderConfigurationResponse(provider=provider, configured=credential is not None, host=credential.host if credential and credential.host else settings.futu_host, port=credential.port if credential and credential.port else settings.futu_port, credentials_present=bool(credential and (credential.api_key_encrypted or credential.secret_encrypted or credential.account_identifier_encrypted)))
    feed = (credential.data_feed if credential and credential.data_feed else settings.alpaca_feed).lower()
    return ProviderConfigurationResponse(provider=provider, configured=credential is not None, host=credential.host if credential and credential.host else settings.alpaca_base_url, port=443, credentials_present=bool(credential and credential.api_key_encrypted and credential.secret_encrypted), data_feed=feed, production_ready=feed == "opra", warning=_alpaca_warning(feed))


async def _check_connection(provider: Literal["IBKR", "FUTU", "ALPACA"], credential: ProviderCredential | None) -> ProviderStatusResponse:
    checked_at = datetime.now(timezone.utc)
    if credential is None:
        feed = get_settings().alpaca_feed if provider == "ALPACA" else None
        return ProviderStatusResponse(provider=provider, configured=False, connected=False, data_feed=feed, production_ready=provider != "ALPACA" or feed == "opra", warning=_alpaca_warning(feed))
    instance = None
    feed = credential.data_feed.lower() if provider == "ALPACA" and credential.data_feed else None
    metadata = {"data_feed": feed, "production_ready": provider != "ALPACA" or feed == "opra", "warning": _alpaca_warning(feed)}
    try:
        instance = create_provider(provider, host=credential.host, port=credential.port, client_id=credential.client_id, api_key=decrypt_credential(credential.api_key_encrypted) if credential.api_key_encrypted else None, secret=decrypt_credential(credential.secret_encrypted) if credential.secret_encrypted else None, data_feed=feed)
        await asyncio.wait_for(instance.connect(), timeout=12)
        connected = await asyncio.wait_for(instance.health_check(), timeout=5)
        return ProviderStatusResponse(provider=provider, configured=True, connected=connected, last_checked_at=checked_at, **metadata)
    except asyncio.TimeoutError:
        return ProviderStatusResponse(provider=provider, configured=True, connected=False, last_checked_at=checked_at, error="Provider connection timed out", **metadata)
    except ProviderError:
        return ProviderStatusResponse(provider=provider, configured=True, connected=False, last_checked_at=checked_at, error="Provider unavailable", **metadata)
    except Exception:
        logger.exception("Unexpected provider health-check failure for %s", provider)
        return ProviderStatusResponse(provider=provider, configured=True, connected=False, last_checked_at=checked_at, error="Provider health check failed", **metadata)
    finally:
        if instance is not None:
            try:
                await asyncio.wait_for(instance.disconnect(), timeout=5)
            except Exception:
                logger.warning("Provider disconnect failed for %s", provider)


@router.get("/status", response_model=ProviderStatusResponse)
async def provider_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ProviderStatusResponse:
    credential = _active_credential(database)
    return await _check_connection(_active_provider_name(database), credential)


@router.post("/configure", response_model=ConfigureProviderResponse)
async def configure_provider(payload: ProviderConfiguration, admin: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ConfigureProviderResponse:
    values = payload.credentials
    try:
        database.query(ProviderCredential).update({ProviderCredential.enabled: False})
        credential = database.query(ProviderCredential).filter_by(provider=payload.provider).first()
        if credential is None:
            credential = ProviderCredential(provider=payload.provider)
            database.add(credential)
        if payload.provider == "ALPACA" and not ((values.api_key and values.secret) or (credential.api_key_encrypted and credential.secret_encrypted)):
            raise HTTPException(status_code=422, detail="Alpaca API Key 和 API Secret 必须同时设置")
        credential.host = get_settings().alpaca_base_url if payload.provider == "ALPACA" else payload.host
        credential.port = payload.port
        credential.client_id = payload.client_id if payload.provider == "IBKR" else None
        credential.data_feed = (payload.data_feed or "indicative") if payload.provider == "ALPACA" else None
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
    return await _check_connection(_active_provider_name(database), credential)


@router.get("/configuration", response_model=ProviderConfigurationResponse)
async def provider_configuration(provider: Optional[Literal["IBKR", "FUTU", "ALPACA"]] = Query(default=None), _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> ProviderConfigurationResponse:
    selected = provider or _active_provider_name(database)
    credential = database.query(ProviderCredential).filter_by(provider=selected).first()
    return _configuration_response(selected, credential)
