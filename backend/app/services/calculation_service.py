"""Persistent calculation-job lifecycle and Celery dispatch boundary."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.database.models import CalculationJob


def create_historical_job(database: Session, start_date: date, end_date: date, frequency: str) -> CalculationJob:
    job = CalculationJob(type="HISTORICAL_SVIX", start_date=start_date, end_date=end_date, frequency=frequency, status="PENDING", progress=0)
    database.add(job)
    database.commit()
    database.refresh(job)
    return job


def dispatch_historical_job(job_id: int) -> None:
    # Delayed import keeps API import lightweight and makes dispatch mockable.
    from app.scheduler.tasks import run_historical_calculation_task

    run_historical_calculation_task.delay(job_id)
