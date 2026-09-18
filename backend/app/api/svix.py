"""Authenticated read-only access to calculated SVIX history."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.config import get_settings
from app.database.database import get_db
from app.database.models import AdminAccount, MarketCollectionRun, SVIXDaily, SVIXHistory, SystemSettings
from app.scheduler.market_hours import market_status, session_bounds
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
    estimated: bool
    source_feed: str | None = None
    calculation_method: str = "legacy"
    market_data_quality: str = "unknown"


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    frequency: Literal["daily", "weekly"] = "daily"


class MarketStatusResponse(BaseModel):
    state: str
    is_collection_window: bool
    session_date: date | None
    market_open: datetime | None
    market_close: datetime | None
    collection_end: datetime | None
    next_open: datetime | None
    last_collection_at: datetime | None
    last_collection_status: str | None
    next_collection_at: datetime | None


def _history_point(record: SVIXHistory) -> SVIXPoint:
    return SVIXPoint(timestamp=record.timestamp, svix=record.svix, core=record.core_vol, memory=record.memory_vol, ai=record.ai_vol, calculation_quality=record.calculation_quality, estimated=record.estimated, source_feed=record.source_feed, calculation_method=record.calculation_method, market_data_quality=record.market_data_quality)


@router.get("/current", response_model=SVIXPoint)
def current_svix(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> SVIXPoint:
    record = SVIXRepository(database).latest()
    if record is None:
        daily = database.query(SVIXDaily).order_by(SVIXDaily.date.desc()).first()
        if daily is None:
            raise HTTPException(status_code=404, detail="No SVIX calculation is available")
        return SVIXPoint(timestamp=daily.close_timestamp or datetime.combine(daily.date, time.min, tzinfo=timezone.utc), svix=daily.svix_close, core=daily.core_close, memory=daily.memory_close, ai=daily.ai_close, calculation_quality=daily.min_calculation_quality, estimated=daily.estimated, source_feed=daily.source_feed)
    return SVIXPoint(timestamp=record.timestamp, svix=record.svix, core=record.core_vol, memory=record.memory_vol, ai=record.ai_vol, calculation_quality=record.calculation_quality, estimated=record.estimated, source_feed=record.source_feed)


@router.get("/history", response_model=list[SVIXPoint])
def svix_history(start_date: date = Query(...), end_date: date = Query(...), frequency: Literal["daily", "weekly"] = "daily", _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> list[SVIXPoint]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    records = SVIXRepository(database).by_time_range(datetime.combine(start_date, time.min, tzinfo=timezone.utc), datetime.combine(end_date, time.max, tzinfo=timezone.utc))
    # The historical dashboard is a daily series. Prefer the latest strict
    # observation for each trading day; only use the latest estimated value
    # when that day has no strict calculation. Full intraday observations are
    # exposed separately by /api/svix/intraday.
    selected_by_date: dict[date, SVIXHistory] = {}
    for record in records:
        calculation_date = record.timestamp.date()
        current = selected_by_date.get(calculation_date)
        if current is None or (current.estimated and not record.estimated) or (current.estimated == record.estimated and record.timestamp > current.timestamp):
            selected_by_date[calculation_date] = record
    detailed_dates = set(selected_by_date)
    daily_records = database.query(SVIXDaily).filter(SVIXDaily.date >= start_date, SVIXDaily.date <= end_date).order_by(SVIXDaily.date.asc()).all()
    points = [_history_point(record) for record in selected_by_date.values()]
    points.extend(SVIXPoint(timestamp=record.close_timestamp or datetime.combine(record.date, time.min, tzinfo=timezone.utc), svix=record.svix_close, core=record.core_close, memory=record.memory_close, ai=record.ai_close, calculation_quality=record.min_calculation_quality, estimated=record.estimated, source_feed=record.source_feed) for record in daily_records if record.date not in detailed_dates)
    points.sort(key=lambda point: point.timestamp)
    if frequency == "weekly":
        by_week: dict[tuple[int, int], SVIXPoint] = {}
        for point in points:
            iso = point.timestamp.isocalendar()
            by_week[(iso.year, iso.week)] = point
        points = list(by_week.values())
    return points


@router.get("/market-status", response_model=MarketStatusResponse)
def current_market_status(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> MarketStatusResponse:
    status = market_status()
    latest = database.query(MarketCollectionRun).order_by(MarketCollectionRun.started_at.desc()).first()
    next_collection = status.next_open
    if status.is_collection_window:
        interval_record = database.query(SystemSettings).filter_by(key="intraday_refresh_seconds").first()
        legacy_interval = database.query(SystemSettings).filter_by(key="refresh_frequency_minutes").first()
        try:
            interval_seconds = int(json.loads(interval_record.value)) if interval_record else (int(json.loads(legacy_interval.value)) * 60 if legacy_interval else get_settings().market_refresh_minutes * 60)
        except (TypeError, ValueError):
            interval_seconds = get_settings().market_refresh_minutes * 60
        now = datetime.now(timezone.utc)
        next_collection = now if latest is None or latest.session_date != status.session_date else max(now, latest.started_at + timedelta(seconds=interval_seconds))
        if status.collection_end and next_collection > status.collection_end:
            next_collection = None
    return MarketStatusResponse(**status.to_dict(), last_collection_at=latest.finished_at if latest else None, last_collection_status=latest.status if latest else None, next_collection_at=next_collection)


@router.get("/intraday", response_model=list[SVIXPoint])
def intraday_svix(session_date: date | None = Query(default=None), _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> list[SVIXPoint]:
    selected_date = session_date or market_status().session_date
    if selected_date is None:
        return []
    bounds = session_bounds(selected_date)
    if bounds is None:
        return []
    start, end = bounds
    records = database.query(SVIXHistory).filter(SVIXHistory.timestamp >= start, SVIXHistory.timestamp <= end).order_by(SVIXHistory.timestamp.asc()).all()
    return [_history_point(record) for record in records]


@router.get("/components")
def svix_components(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, float]:
    record = SVIXRepository(database).latest()
    if record is None:
        daily = database.query(SVIXDaily).order_by(SVIXDaily.date.desc()).first()
        if daily is None:
            raise HTTPException(status_code=404, detail="No SVIX calculation is available")
        return {"core": daily.core_close, "memory": daily.memory_close, "ai": daily.ai_close}
    return {"core": record.core_vol, "memory": record.memory_vol, "ai": record.ai_vol}


@router.post("/calculate")
def calculate_history(payload: CalculationRequest, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> dict[str, object]:
    results = calculate_svix(database, payload.start_date, payload.end_date, payload.frequency)
    return {"status": "completed", "records_calculated": len(results)}
