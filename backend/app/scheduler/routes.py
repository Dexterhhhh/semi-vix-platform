"""Loopback-only endpoints used by the Go scheduler.

Nginx exposes only /api and /health, so these routes are reachable solely on
the FastAPI listener bound to 127.0.0.1 inside the application container.
"""

from fastapi import APIRouter

from app.scheduler.runner import run_maintenance, run_pending_job
from app.scheduler.tasks import collect_market_data_task

router = APIRouter(prefix="/internal/scheduler", include_in_schema=False)


@router.post("/market")
def market() -> dict[str, object]:
    return collect_market_data_task()


@router.post("/jobs")
def jobs() -> dict[str, object]:
    return run_pending_job()


@router.post("/maintenance")
def maintenance() -> dict[str, object]:
    return run_maintenance()
