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
        # The task itself reads the live interval from PostgreSQL and checks the
        # NYSE session. A one-minute heartbeat makes panel changes effective
        # without restarting Celery Beat.
        "market-refresh": {"task": "app.scheduler.tasks.collect_market_data_task", "schedule": 10},
        "data-lifecycle-maintenance": {"task": "app.scheduler.tasks.data_lifecycle_maintenance_task", "schedule": 15 * 60},
    },
)
