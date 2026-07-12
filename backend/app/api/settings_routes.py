"""Non-sensitive analytical settings and system status endpoints."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AdminAccount, CalculationJob, ProviderCredential, SVIXHistory, SystemSettings
from app.data.universe import DEFAULT_SYMBOLS

router = APIRouter(prefix="/api/settings", tags=["settings"])
ALLOWED_KEYS = {"refresh_frequency_minutes", "selected_symbols", "manual_component_weights"}


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_frequency_minutes: int = Field(default=15, ge=5, le=1440)
    selected_symbols: list[str] = Field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    manual_component_weights: Optional[dict[str, float]] = None


def _load(database: Session) -> SettingsPayload:
    values = {item.key: json.loads(item.value) for item in database.query(SystemSettings).filter(SystemSettings.key.in_(ALLOWED_KEYS)).all()}
    settings = get_settings()
    return SettingsPayload(refresh_frequency_minutes=values.get("refresh_frequency_minutes", settings.market_refresh_minutes), selected_symbols=values.get("selected_symbols", list(DEFAULT_SYMBOLS)), manual_component_weights=values.get("manual_component_weights"))


@router.get("", response_model=SettingsPayload)
def get_settings_route(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> SettingsPayload:
    return _load(database)


@router.put("", response_model=SettingsPayload)
def update_settings(payload: SettingsPayload, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> SettingsPayload:
    for key, value in payload.model_dump().items():
        record = database.query(SystemSettings).filter_by(key=key).first()
        if record is None:
            database.add(SystemSettings(key=key, value=json.dumps(value)))
        else:
            record.value = json.dumps(value)
    database.commit()
    return _load(database)


@router.get("/system-status")
def system_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, Any]:
    database.execute(text("SELECT 1"))
    credential = database.query(ProviderCredential).filter_by(enabled=True).first()
    latest = database.query(SVIXHistory).order_by(SVIXHistory.timestamp.desc()).first()
    recent_job = database.query(CalculationJob).order_by(CalculationJob.created_at.desc()).first()
    return {
        "database": "OK",
        "market_data": "Configured" if credential else "Not configured",
        "svix_engine": "Ready",
        "worker": "Queued" if recent_job and recent_job.status in {"PENDING", "RUNNING"} else "Idle",
        "last_calculation": latest.timestamp if latest else None,
    }
