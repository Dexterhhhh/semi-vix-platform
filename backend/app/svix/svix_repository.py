"""Persistence boundary for calculation results."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models import SVIXHistory
from app.svix.models import SVIXResult


class SVIXRepository:
    def __init__(self, database: Session):
        self.database = database

    def save(self, result: SVIXResult) -> SVIXHistory:
        record = self.database.query(SVIXHistory).filter_by(timestamp=result.timestamp).first()
        if record is None:
            record = SVIXHistory(timestamp=result.timestamp, svix=result.svix, core_vol=result.core_vol, memory_vol=result.memory_vol, ai_vol=result.ai_vol, calculation_quality=result.calculation_quality)
            self.database.add(record)
            return record
        record.svix = result.svix
        record.core_vol = result.core_vol
        record.memory_vol = result.memory_vol
        record.ai_vol = result.ai_vol
        record.calculation_quality = result.calculation_quality
        return record

    def latest(self) -> SVIXHistory | None:
        return self.database.query(SVIXHistory).order_by(SVIXHistory.timestamp.desc()).first()

    def by_time_range(self, start: datetime, end: datetime) -> list[SVIXHistory]:
        return self.database.query(SVIXHistory).filter(SVIXHistory.timestamp >= start, SVIXHistory.timestamp <= end).order_by(SVIXHistory.timestamp.asc()).all()
