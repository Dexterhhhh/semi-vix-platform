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
from app.database.models import AdminAccount, CalculationJob, ProviderCredential
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
    active_provider = database.query(ProviderCredential).filter_by(enabled=True).first()
    if active_provider and active_provider.provider == "ALPACA" and payload.start_date < date(2024, 2, 1):
        raise HTTPException(status_code=422, detail="Alpaca 期权历史数据仅支持 2024-02-01 之后的日期")
    duplicate = database.query(CalculationJob).filter(
        CalculationJob.type == "HISTORICAL_SVIX",
        CalculationJob.start_date == payload.start_date,
        CalculationJob.end_date == payload.end_date,
        CalculationJob.frequency == payload.frequency,
        CalculationJob.status.in_(("PENDING", "RUNNING")),
    ).first()
    if duplicate is not None:
        raise HTTPException(status_code=409, detail=f"相同范围的历史计算任务 #{duplicate.id} 已在运行")
    job = create_historical_job(database, payload.start_date, payload.end_date, payload.frequency)
    try:
        dispatch_historical_job(job.id)
    except Exception:
        job.status = "DISPATCH_FAILED"
        job.error_message = "任务分发失败；可在队列恢复后重试"
        database.commit()
    return _response(job)


@router.post("/{job_id}/retry", response_model=JobResponse, status_code=202)
def retry_job(job_id: int, _: AdminAccount = Depends(get_current_admin), database: Session = Depends(get_db)) -> JobResponse:
    job = database.get(CalculationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Calculation job not found")
    if job.status not in {"DISPATCH_FAILED", "FAILED", "NO_VALID_DATA"}:
        raise HTTPException(status_code=409, detail="只有分发失败、执行失败或无有效数据的任务可以重试")
    job.status = "PENDING"
    job.progress = 0
    job.started_at = None
    job.finished_at = None
    job.error_message = None
    database.commit()
    try:
        dispatch_historical_job(job.id)
    except Exception:
        job.status = "DISPATCH_FAILED"
        job.error_message = "任务分发失败；可在队列恢复后重试"
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
