"""Non-sensitive analytical, retention and system settings endpoints."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AdminAccount, CalculationJob, DataMaintenanceRun, OptionSnapshot, ProviderCredential, SVIXDaily, SVIXHistory, SystemSettings
from app.data.universe import DEFAULT_SYMBOLS

router = APIRouter(prefix="/api/settings", tags=["settings"])
ALLOWED_KEYS = {"refresh_frequency_minutes", "selected_symbols", "manual_component_weights", "option_cleanup_enabled", "option_retention_days", "svix_downsample_enabled", "detailed_retention_days", "maintenance_time_utc"}


class SettingsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_frequency_minutes: int = Field(default=15, ge=5, le=1440)
    selected_symbols: list[str] = Field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    manual_component_weights: Optional[dict[str, float]] = None
    option_cleanup_enabled: bool = True
    option_retention_days: int = Field(default=3, ge=1, le=30)
    svix_downsample_enabled: bool = True
    detailed_retention_days: int = Field(default=7, ge=1, le=365)
    maintenance_time_utc: str = "03:30"

    @field_validator("maintenance_time_utc")
    @classmethod
    def valid_time(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("must use HH:MM") from exc
        return value


def _load(database: Session) -> SettingsPayload:
    values = {item.key: json.loads(item.value) for item in database.query(SystemSettings).filter(SystemSettings.key.in_(ALLOWED_KEYS)).all()}
    settings = get_settings()
    return SettingsPayload(
        refresh_frequency_minutes=values.get("refresh_frequency_minutes", settings.market_refresh_minutes),
        selected_symbols=values.get("selected_symbols", list(DEFAULT_SYMBOLS)),
        manual_component_weights=values.get("manual_component_weights"),
        option_cleanup_enabled=values.get("option_cleanup_enabled", True),
        option_retention_days=values.get("option_retention_days", 3),
        svix_downsample_enabled=values.get("svix_downsample_enabled", True),
        detailed_retention_days=values.get("detailed_retention_days", 7),
        maintenance_time_utc=values.get("maintenance_time_utc", "03:30"),
    )


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


def _table_size(database: Session, table_name: str) -> Optional[int]:
    if database.bind is None or database.bind.dialect.name != "postgresql":
        return None
    return int(database.execute(text(f"SELECT pg_total_relation_size('{table_name}')")).scalar_one())


@router.get("/data-lifecycle/status")
def lifecycle_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, Any]:
    latest = database.query(DataMaintenanceRun).order_by(DataMaintenanceRun.started_at.desc()).first()
    return {
        "option_snapshot_rows": database.query(func.count(OptionSnapshot.id)).scalar() or 0,
        "option_snapshot_bytes": _table_size(database, "option_snapshot"),
        "svix_history_rows": database.query(func.count(SVIXHistory.id)).scalar() or 0,
        "svix_history_bytes": _table_size(database, "svix_history"),
        "svix_daily_rows": database.query(func.count(SVIXDaily.id)).scalar() or 0,
        "svix_daily_bytes": _table_size(database, "svix_daily"),
        "last_run": None if latest is None else {
            "status": latest.status,
            "started_at": latest.started_at,
            "finished_at": latest.finished_at,
            "option_rows_deleted": latest.option_rows_deleted,
            "history_rows_aggregated": latest.history_rows_aggregated,
            "daily_rows_written": latest.daily_rows_written,
        },
    }


@router.post("/data-lifecycle/run", status_code=202)
def run_lifecycle_now(_: AdminAccount = Depends(get_current_admin)) -> dict[str, str]:
    from app.scheduler.tasks import data_lifecycle_maintenance_task
    data_lifecycle_maintenance_task.delay(True)
    return {"status": "queued"}


@router.get("/system-status")
def system_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, Any]:
    database.execute(text("SELECT 1"))
    credential = database.query(ProviderCredential).filter_by(enabled=True).first()
    latest = database.query(SVIXHistory).order_by(SVIXHistory.timestamp.desc()).first()
    latest_daily = database.query(SVIXDaily).order_by(SVIXDaily.date.desc()).first()
    recent_job = database.query(CalculationJob).order_by(CalculationJob.created_at.desc()).first()
    last_calculation = latest.timestamp if latest else latest_daily.date if latest_daily else None
    return {"database": "OK", "market_data": "Configured" if credential else "Not configured", "svix_engine": "Ready", "worker": "Queued" if recent_job and recent_job.status in {"PENDING", "RUNNING"} else "Idle", "last_calculation": last_calculation}
