"""Authenticated historical calculation job management."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.jwt import get_current_admin
from app.database.database import get_db
from app.database.models import AdminAccount, CalculationJob
from app.services.calculation_service import create_historical_job, dispatch_historical_job

router = APIRouter(prefix="/api/jobs", tags=["calculation-jobs"])


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    frequency: Literal["daily", "weekly"] = "daily"


class JobResponse(BaseModel):
    id: int
    type: str
    start_date: date
    end_date: date
    frequency: str
    status: str
    progress: int
    result_summary: Optional[dict] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None


def _response(job: CalculationJob) -> JobResponse:
    summary = json.loads(job.result_summary) if job.result_summary else None
    return JobResponse(id=job.id, type=job.type, start_date=job.start_date, end_date=job.end_date, frequency=job.frequency, status=job.status, progress=job.progress, result_summary=summary, created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at, error_message=job.error_message)


@router.post("/create", response_model=JobResponse, status_code=202)
def create_job(payload: JobCreateRequest, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> JobResponse:
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="end_date must not be before start_date")
    job = create_historical_job(database, payload.start_date, payload.end_date, payload.frequency)
    try:
        dispatch_historical_job(job.id)
    except Exception:
        # Job remains visible and retryable even if Redis is temporarily unavailable.
        job.error_message = "Task dispatch pending"
        database.commit()
    return _response(job)


@router.get("", response_model=list[JobResponse])
def list_jobs(limit: int = Query(default=20, ge=1, le=100), _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> list[JobResponse]:
    jobs = database.query(CalculationJob).order_by(CalculationJob.created_at.desc()).limit(limit).all()
    return [_response(job) for job in jobs]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> JobResponse:
    job = database.get(CalculationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Calculation job not found")
    return _response(job)
