"""Loopback vendor SDK health checks, without public API or auth dependencies."""

import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter
from app.config import get_settings
from app.data.vendor_factory import create_vendor_provider
from app.database.database import SessionLocal
from app.database.models import ProviderCredential

router = APIRouter(prefix="/internal/providers", include_in_schema=False)


@router.post("/status")
async def status():
    database = SessionLocal()
    instance = None
    try:
        credential = database.query(ProviderCredential).filter_by(enabled=True).first()
        provider = credential.provider if credential else get_settings().data_provider
        result = {"provider": provider, "configured": credential is not None,
                  "connected": False, "last_checked_at": None, "error": None,
                  "data_feed": None, "production_ready": True, "warning": None}
        if credential is None:
            return result
        result["last_checked_at"] = datetime.now(timezone.utc)
        if provider == "ALPACA":
            result["error"] = "Alpaca is handled by Go"
            return result
        instance = create_vendor_provider(provider, host=credential.host, port=credential.port,
                                          client_id=credential.client_id)
        await asyncio.wait_for(instance.connect(), timeout=12)
        result["connected"] = await asyncio.wait_for(instance.health_check(), timeout=5)
        return result
    except Exception:
        result["error"] = "Provider unavailable"
        return result
    finally:
        if instance is not None:
            try:
                await asyncio.wait_for(instance.disconnect(), timeout=5)
            except Exception:
                pass
        database.close()
