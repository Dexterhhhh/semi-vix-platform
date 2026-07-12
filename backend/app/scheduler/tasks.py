"""Retryable worker tasks.  No task loop runs inside the FastAPI process."""

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import logging
import time

from app.database.database import SessionLocal
from app.database.models import CalculationJob
from app.data.exceptions import ProviderUnavailableError
from app.scheduler.celery_app import celery_app
from app.services.market_refresh import refresh_market_data
from app.services.svix_calculator import calculate_svix

logger = logging.getLogger(__name__)


def _log(task: str, status: str, started: float, **details: object) -> None:
    logger.info(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "service": "worker", "task": task, "status": status, "duration": round(time.monotonic() - started, 3), **details}, default=str))


@celery_app.task(bind=True, autoretry_for=(ConnectionError, TimeoutError, ProviderUnavailableError), retry_backoff=True, retry_backoff_max=300, retry_kwargs={"max_retries": 5})
def collect_market_data_task(self) -> dict[str, object]:
    started = time.monotonic()
    try:
        summary = refresh_market_data()
        _log("collect_market_data", "success", started, summary=summary)
        return summary
    except Exception as exc:
        _log("collect_market_data", "failed", started, error=type(exc).__name__)
        raise


@celery_app.task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_backoff_max=300, retry_kwargs={"max_retries": 3})
def run_historical_calculation_task(self, job_id: int) -> dict[str, object]:
    started = time.monotonic()
    database = SessionLocal()
    try:
        job = database.get(CalculationJob, job_id)
        if job is None:
            return {"job_id": job_id, "status": "MISSING"}
        if job.status == "CANCELLED":
            return {"job_id": job_id, "status": "CANCELLED"}
        job.status, job.progress, job.started_at, job.error_message = "RUNNING", 10, datetime.now(timezone.utc), None
        database.commit()
        results = calculate_svix(database, job.start_date, job.end_date, job.frequency)
        job.status, job.progress, job.finished_at = "COMPLETED", 100, datetime.now(timezone.utc)
        job.result_summary = json.dumps({"records_calculated": len(results)})
        database.commit()
        result = {"job_id": job_id, "status": job.status, "records_calculated": len(results)}
        _log("historical_calculation", "success", started, job_id=job_id, records_calculated=len(results))
        return result
    except Exception as exc:
        database.rollback()
        job = database.get(CalculationJob, job_id)
        if job is not None:
            job.status, job.progress, job.finished_at, job.error_message = "FAILED", 100, datetime.now(timezone.utc), "Calculation failed"
            database.commit()
        _log("historical_calculation", "failed", started, job_id=job_id, error=type(exc).__name__)
        raise
    finally:
        database.close()


@celery_app.task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_backoff_max=300, retry_kwargs={"max_retries": 3})
def calculate_latest_svix_task(self) -> dict[str, object]:
    """Scheduled best-effort calculation from the latest available snapshot day."""
    today = date.today()
    database = SessionLocal()
    try:
        results = calculate_svix(database, today, today, "daily")
        return {"records_calculated": len(results)}
    finally:
        database.close()
