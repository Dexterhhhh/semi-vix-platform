"""Single-owner custom volatility-index configuration and results API."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.database.database import get_db
from app.database.models import AdminAccount, AuditEvent, CustomIndex, CustomIndexComponent, CustomIndexDaily, CustomIndexHistory, CustomIndexVersion
from app.scheduler.market_hours import market_status, session_bounds
from app.services.custom_index import latest_definition, next_version_number

router = APIRouter(prefix="/api/custom-index", tags=["custom-index"])
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.-]{0,15}$")


class ComponentPayload(BaseModel):
    symbol: str
    weight_percent: float = Field(gt=0, le=100)

    @field_validator("symbol")
    @classmethod
    def valid_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not SYMBOL_PATTERN.fullmatch(normalized):
            raise ValueError("invalid US market symbol")
        return normalized


class CustomIndexPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    enabled: bool = True
    missing_policy: Literal["STRICT", "RENORMALIZE"] = "STRICT"
    components: list[ComponentPayload] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def valid_components(self):
        symbols = [item.symbol for item in self.components]
        if len(symbols) != len(set(symbols)):
            raise ValueError("component symbols must be unique")
        if abs(sum(item.weight_percent for item in self.components) - 100.0) > 0.01:
            raise ValueError("component weights must total 100%")
        self.name = self.name.strip()
        return self


class CustomIndexConfigResponse(CustomIndexPayload):
    id: int
    version: int
    updated_at: datetime


class CustomIndexPoint(BaseModel):
    timestamp: datetime
    value: float
    calculation_quality: float
    estimated: bool
    source_feed: str | None = None
    version: int


def _config(database: Session) -> tuple[CustomIndex, CustomIndexVersion, list[CustomIndexComponent]] | None:
    index = database.query(CustomIndex).order_by(CustomIndex.id).first()
    if index is None:
        return None
    definition = latest_definition(database, index)
    if definition is None:
        return None
    components = database.query(CustomIndexComponent).filter_by(version_id=definition.version.id).order_by(CustomIndexComponent.id).all()
    return index, definition.version, components


def _response(index: CustomIndex, version: CustomIndexVersion, components: list[CustomIndexComponent]) -> CustomIndexConfigResponse:
    return CustomIndexConfigResponse(id=index.id, version=version.version_number, name=index.name, enabled=index.enabled, missing_policy=index.missing_policy, components=[ComponentPayload(symbol=item.symbol, weight_percent=item.weight * 100.0) for item in components], updated_at=index.updated_at)


@router.get("", response_model=CustomIndexConfigResponse | None)
def get_custom_index(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)):
    config = _config(database)
    return None if config is None else _response(*config)


@router.put("", response_model=CustomIndexConfigResponse)
def save_custom_index(payload: CustomIndexPayload, admin: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)):
    existing = _config(database)
    if existing is None:
        index = CustomIndex(name=payload.name, enabled=payload.enabled, missing_policy=payload.missing_policy)
        database.add(index)
        database.flush()
        changed = True
    else:
        index, current_version, current_components = existing
        current = {item.symbol: round(item.weight, 12) for item in current_components}
        incoming = {item.symbol: round(item.weight_percent / 100.0, 12) for item in payload.components}
        changed = current != incoming or current_version.name != payload.name or current_version.missing_policy != payload.missing_policy
        index.name, index.enabled, index.missing_policy = payload.name, payload.enabled, payload.missing_policy
    if changed:
        version = CustomIndexVersion(custom_index_id=index.id, version_number=next_version_number(database, index.id), name=payload.name, missing_policy=payload.missing_policy)
        database.add(version)
        database.flush()
        database.add_all([CustomIndexComponent(version_id=version.id, symbol=item.symbol, weight=item.weight_percent / 100.0) for item in payload.components])
    database.add(AuditEvent(admin_id=admin.id, action="custom_index.updated"))
    database.commit()
    config = _config(database)
    if config is None:
        raise HTTPException(status_code=500, detail="Custom index persistence failed")
    return _response(*config)


def _point(row: CustomIndexHistory, version: int) -> CustomIndexPoint:
    return CustomIndexPoint(timestamp=row.timestamp, value=row.value, calculation_quality=row.calculation_quality, estimated=row.estimated, source_feed=row.source_feed, version=version)


@router.get("/current", response_model=CustomIndexPoint)
def current_custom_index(_: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)):
    config = _config(database)
    if config is None:
        raise HTTPException(404, "Custom index is not configured")
    index, version, _ = config
    row = database.query(CustomIndexHistory).filter_by(custom_index_id=index.id, version_id=version.id).order_by(CustomIndexHistory.timestamp.desc()).first()
    if row is None:
        daily = database.query(CustomIndexDaily).filter_by(custom_index_id=index.id, version_id=version.id).order_by(CustomIndexDaily.date.desc()).first()
        if daily is None:
            raise HTTPException(404, "No custom index calculation is available")
        return CustomIndexPoint(timestamp=daily.close_timestamp or datetime.combine(daily.date, time.min, tzinfo=timezone.utc), value=daily.value_close, calculation_quality=daily.min_calculation_quality, estimated=daily.estimated, source_feed=daily.source_feed, version=version.version_number)
    return _point(row, version.version_number)


@router.get("/history", response_model=list[CustomIndexPoint])
def custom_index_history(start_date: date = Query(...), end_date: date = Query(...), _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)):
    if end_date < start_date:
        raise HTTPException(422, "end_date must not be before start_date")
    config = _config(database)
    if config is None:
        return []
    index, version, _ = config
    rows = database.query(CustomIndexHistory).filter(CustomIndexHistory.custom_index_id == index.id, CustomIndexHistory.version_id == version.id, CustomIndexHistory.timestamp >= datetime.combine(start_date, time.min, tzinfo=timezone.utc), CustomIndexHistory.timestamp <= datetime.combine(end_date, time.max, tzinfo=timezone.utc)).order_by(CustomIndexHistory.timestamp).all()
    selected = {}
    for row in rows:
        current = selected.get(row.timestamp.date())
        if current is None or (current.estimated and not row.estimated) or (current.estimated == row.estimated and row.timestamp > current.timestamp):
            selected[row.timestamp.date()] = row
    points = [_point(row, version.version_number) for row in selected.values()]
    detailed_dates = set(selected)
    daily = database.query(CustomIndexDaily).filter(CustomIndexDaily.custom_index_id == index.id, CustomIndexDaily.version_id == version.id, CustomIndexDaily.date >= start_date, CustomIndexDaily.date <= end_date).all()
    points.extend(CustomIndexPoint(timestamp=row.close_timestamp or datetime.combine(row.date, time.min, tzinfo=timezone.utc), value=row.value_close, calculation_quality=row.min_calculation_quality, estimated=row.estimated, source_feed=row.source_feed, version=version.version_number) for row in daily if row.date not in detailed_dates)
    return sorted(points, key=lambda point: point.timestamp)


@router.get("/intraday", response_model=list[CustomIndexPoint])
def custom_index_intraday(session_date: date | None = Query(None), _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)):
    config = _config(database)
    selected_date = session_date or market_status().session_date
    if config is None or selected_date is None or (bounds := session_bounds(selected_date)) is None:
        return []
    index, version, _ = config
    rows = database.query(CustomIndexHistory).filter(CustomIndexHistory.custom_index_id == index.id, CustomIndexHistory.version_id == version.id, CustomIndexHistory.timestamp >= bounds[0], CustomIndexHistory.timestamp <= bounds[1]).order_by(CustomIndexHistory.timestamp).all()
    return [_point(row, version.version_number) for row in rows]
