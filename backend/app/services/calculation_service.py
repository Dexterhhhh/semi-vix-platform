"""Persistent calculation-job lifecycle consumed by the Go scheduler."""

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
    # The database row is the durable queue. The Go scheduler polls PENDING
    # jobs, so dispatch cannot be lost when an in-memory broker restarts.
    if job_id <= 0:
        raise ValueError("job_id must be positive")


def recover_interrupted_jobs(database: Session) -> int:
    """Return jobs abandoned by a previous API process to the durable queue."""
    jobs = database.query(CalculationJob).filter_by(status="RUNNING").all()
    for job in jobs:
        job.status = "PENDING"
        job.progress = 0
        job.started_at = None
        job.error_message = None
    if jobs:
        database.commit()
    return len(jobs)
