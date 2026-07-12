"""Celery application kept separate from FastAPI request processing."""

from celery import Celery

from app.config import get_settings

settings = get_settings()
celery_app = Celery("semi_vix", broker=settings.redis_url, backend=settings.redis_url, include=["app.scheduler.tasks"])
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "market-refresh": {"task": "app.scheduler.tasks.collect_market_data_task", "schedule": settings.market_refresh_minutes * 60},
        "svix-latest-calculation": {"task": "app.scheduler.tasks.calculate_latest_svix_task", "schedule": settings.svix_calculation_minutes * 60},
    },
)
