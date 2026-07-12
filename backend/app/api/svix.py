"""Authenticated read-only access to calculated SVIX history."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.database.database import get_db
from app.database.models import AdminAccount
from app.services.svix_calculator import calculate_svix
from app.svix.svix_repository import SVIXRepository

router = APIRouter(prefix="/api/svix", tags=["svix"])


class SVIXPoint(BaseModel):
    timestamp: datetime
    svix: float
    core: float
    memory: float
    ai: float
    calculation_quality: float


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    frequency: Literal["daily", "weekly"] = "daily"


@router.get("/current", response_model=SVIXPoint)
def current_svix(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> SVIXPoint:
    record = SVIXRepository(database).latest()
    if record is None:
        raise HTTPException(status_code=404, detail="No SVIX calculation is available")
    return SVIXPoint(timestamp=record.timestamp, svix=record.svix, core=record.core_vol, memory=record.memory_vol, ai=record.ai_vol, calculation_quality=record.calculation_quality)


@router.get("/history", response_model=list[SVIXPoint])
def svix_history(start_date: date = Query(...), end_date: date = Query(...), frequency: Literal["daily", "weekly"] = "daily", _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> list[SVIXPoint]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    records = SVIXRepository(database).by_time_range(datetime.combine(start_date, time.min, tzinfo=timezone.utc), datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    if frequency == "weekly":
        records = [record for record in records if record.timestamp.weekday() == 4]
    return [SVIXPoint(timestamp=record.timestamp, svix=record.svix, core=record.core_vol, memory=record.memory_vol, ai=record.ai_vol, calculation_quality=record.calculation_quality) for record in records]


@router.get("/components")
def svix_components(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, float]:
    record = SVIXRepository(database).latest()
    if record is None:
        raise HTTPException(status_code=404, detail="No SVIX calculation is available")
    return {"core": record.core_vol, "memory": record.memory_vol, "ai": record.ai_vol}


@router.post("/calculate")
def calculate_history(payload: CalculationRequest, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, object]:
    results = calculate_svix(database, payload.start_date, payload.end_date, payload.frequency)
    return {"status": "completed", "records_calculated": len(results)}
