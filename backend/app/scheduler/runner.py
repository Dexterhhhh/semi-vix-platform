"""Database-backed operations called by the in-container Go scheduler."""

from __future__ import annotations

import json

from app.database.database import SessionLocal
from app.database.models import CalculationJob, SystemSettings
from app.scheduler.tasks import collect_market_data_task, data_lifecycle_maintenance_task, run_historical_calculation_task


def run_pending_job() -> dict[str, object]:
    database = SessionLocal()
    try:
        job = database.query(CalculationJob).filter_by(status="PENDING").order_by(CalculationJob.created_at.asc()).first()
        job_id = job.id if job else None
    finally:
        database.close()
    return {"status": "IDLE"} if job_id is None else run_historical_calculation_task(job_id)


def run_maintenance() -> dict[str, object]:
    database = SessionLocal()
    try:
        requested = database.query(SystemSettings).filter_by(key="maintenance_requested").first()
        try:
            force = bool(requested and json.loads(requested.value))
        except (TypeError, ValueError):
            force = False
    finally:
        database.close()
    result = data_lifecycle_maintenance_task(force=force)
    if force:
        database = SessionLocal()
        try:
            requested = database.query(SystemSettings).filter_by(key="maintenance_requested").first()
            if requested is not None:
                requested.value = "false"
                database.commit()
        finally:
            database.close()
    return result
