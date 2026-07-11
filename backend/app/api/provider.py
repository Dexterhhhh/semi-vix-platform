import logging
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.auth.jwt import get_current_admin
from app.data.credentials import encrypt_credential
from app.data.exceptions import ProviderError
from app.data.factory import create_provider
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AdminAccount, ProviderCredential

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/provider", tags=["market-data provider"])


class CredentialInput(BaseModel):
    api_key: Optional[str] = Field(default=None, max_length=2048)
    secret: Optional[str] = Field(default=None, max_length=2048)
    account_identifier: Optional[str] = Field(default=None, max_length=2048)


class ProviderConfiguration(BaseModel):
    provider: Literal["IBKR", "FUTU"]
    credentials: CredentialInput = Field(default_factory=CredentialInput)


def _active_provider_name(database: Session) -> str:
    credential = database.query(ProviderCredential).filter_by(enabled=True).first()
    return credential.provider if credential else get_settings().data_provider.upper()


@router.get("/status")
async def provider_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, object]:
    name = _active_provider_name(database)
    try:
        provider = create_provider(name)
        await provider.connect()
        connected = await provider.health_check()
        await provider.disconnect()
        return {"provider": name, "connected": connected}
    except ProviderError as exc:
        logger.warning("Provider %s unavailable: %s", name, exc)
        return {"provider": name, "connected": False}
    except Exception:
        logger.exception("Unexpected provider health-check failure for %s", name)
        return {"provider": name, "connected": False}


@router.post("/configure")
async def configure_provider(payload: ProviderConfiguration, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, object]:
    database.query(ProviderCredential).update({ProviderCredential.enabled: False})
    credential = database.query(ProviderCredential).filter_by(provider=payload.provider).first()
    values = payload.credentials
    if credential is None:
        credential = ProviderCredential(provider=payload.provider)
        database.add(credential)
    credential.api_key_encrypted = encrypt_credential(values.api_key) if values.api_key else None
    credential.secret_encrypted = encrypt_credential(values.secret) if values.secret else None
    credential.account_identifier_encrypted = encrypt_credential(values.account_identifier) if values.account_identifier else None
    credential.enabled = True
    database.commit()
    return {"provider": credential.provider, "enabled": True}
