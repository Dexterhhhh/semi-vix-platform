"""Retryable worker tasks.  No task loop runs inside the FastAPI process."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import time

from sqlalchemy import func

from app.database.database import SessionLocal
from app.database.models import CalculationJob, MarketCollectionRun, OptionSnapshot, ProviderCredential, SystemSettings
from app.data.exceptions import ProviderUnavailableError
from app.scheduler.celery_app import celery_app
from app.scheduler.market_hours import market_status
from app.services.market_refresh import refresh_market_data
from app.services.svix_calculator import calculate_svix
from app.services.data_lifecycle import run_data_maintenance
from app.services.alpaca_history import backfill_alpaca_history
from app.svix.universe import DEFAULT_UNIVERSE
from app.services.custom_index import custom_symbols

logger = logging.getLogger(__name__)


def _job_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name == "ProviderPermissionError" and "OPRA" in str(exc).upper():
        return "Alpaca 免费账户拒绝了实时 OPRA 数据；系统已改用延迟历史日线，请重试任务"
    messages = {
        "ProviderPermissionError": "Alpaca 凭据无效，或账户无权访问所请求的历史数据",
        "ProviderUnavailableError": "Alpaca 历史数据服务暂时不可用",
        "InsufficientCorrelationData": "历史标的日线不足 253 个交易日",
        "MissingExpiry": "期权数据无法覆盖 30 日到期期限",
    }
    return messages.get(name, f"计算失败（{name}）")


def _selected_symbols(database) -> tuple[str, ...]:
    record = database.query(SystemSettings).filter_by(key="selected_symbols").first()
    if not record:
        return tuple(dict.fromkeys((*DEFAULT_UNIVERSE, *custom_symbols(database))))
    try:
        selected = tuple(symbol for symbol in json.loads(record.value) if symbol in DEFAULT_UNIVERSE)
        base = selected or DEFAULT_UNIVERSE
        return tuple(dict.fromkeys((*base, *custom_symbols(database))))
    except (TypeError, ValueError):
        return tuple(dict.fromkeys((*DEFAULT_UNIVERSE, *custom_symbols(database))))


def _log(task: str, status: str, started: float, **details: object) -> None:
    logger.info(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "service": "worker", "task": task, "status": status, "duration": round(time.monotonic() - started, 3), **details}, default=str))


@celery_app.task(bind=True, autoretry_for=(ConnectionError, TimeoutError, ProviderUnavailableError), retry_backoff=True, retry_backoff_max=300, retry_kwargs={"max_retries": 5})
def collect_market_data_task(self) -> dict[str, object]:
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    market = market_status(now)
    if not market.is_collection_window or market.session_date is None:
        result = {"status": "SKIPPED", "reason": "market_closed", "market": market.to_dict()}
        _log("collect_market_data", "skipped", started, reason="market_closed", market_state=market.state)
        return result
    database = SessionLocal()
    run: MarketCollectionRun | None = None
    try:
        interval_record = database.query(SystemSettings).filter_by(key="intraday_refresh_seconds").first()
        legacy_interval = database.query(SystemSettings).filter_by(key="refresh_frequency_minutes").first()
        try:
            interval_seconds = int(json.loads(interval_record.value)) if interval_record else (int(json.loads(legacy_interval.value)) * 60 if legacy_interval else 900)
        except (TypeError, ValueError):
            interval_seconds = 900
        interval_seconds = min(3600, max(30, interval_seconds))
        interval_minutes = max(1, (interval_seconds + 59) // 60)
        latest = database.query(MarketCollectionRun).filter_by(session_date=market.session_date).order_by(MarketCollectionRun.started_at.desc()).first()
        if latest and latest.status == "RUNNING" and latest.started_at >= now - timedelta(seconds=max(1800, interval_seconds * 2)):
            return {"status": "SKIPPED", "reason": "collection_running", "market": market.to_dict()}
        if latest and latest.status == "RUNNING":
            latest.status, latest.finished_at, latest.error_message = "FAILED", now, "stale collection run"
            database.commit()
        if latest and latest.status == "COMPLETED" and latest.started_at > now - timedelta(seconds=interval_seconds):
            return {"status": "SKIPPED", "reason": "interval_not_due", "next_due": (latest.started_at + timedelta(seconds=interval_seconds)).isoformat(), "market": market.to_dict()}
        run = MarketCollectionRun(session_date=market.session_date, status="RUNNING", interval_minutes=interval_minutes, interval_seconds=interval_seconds, started_at=now)
        database.add(run)
        database.commit()
        summary = refresh_market_data()
        run = database.get(MarketCollectionRun, run.id)
        run.status = "COMPLETED"
        run.finished_at = datetime.now(timezone.utc)
        run.stock_quotes_saved = int(summary.get("stock_quotes_saved", 0))
        run.option_quotes_saved = int(summary.get("option_quotes_saved", 0))
        run.symbols_succeeded = int(summary.get("symbols_succeeded", 0))
        run.symbols_failed = int(summary.get("symbols_failed", 0))
        database.commit()
        if run.option_quotes_saved > 0:
            calculate_latest_svix_task.delay()
        _log("collect_market_data", "success", started, summary=summary)
        return {**summary, "status": "COMPLETED", "market": market.to_dict(), "interval_seconds": interval_seconds}
    except Exception as exc:
        database.rollback()
        if run is not None:
            failed = database.get(MarketCollectionRun, run.id)
            if failed is not None:
                failed.status, failed.finished_at, failed.error_message = "FAILED", datetime.now(timezone.utc), type(exc).__name__
                database.commit()
        _log("collect_market_data", "failed", started, error=type(exc).__name__)
        raise
    finally:
        database.close()


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
        provider = database.query(ProviderCredential).filter_by(enabled=True).first()
        backfill_summary: dict[str, int] = {}
        if provider and provider.provider == "ALPACA":
            def update_progress(percent: int, stage: str) -> None:
                job.progress = percent
                job.result_summary = json.dumps({"stage": stage})
                database.commit()

            backfill_summary = backfill_alpaca_history(database, job.start_date, job.end_date, _selected_symbols(database), update_progress)
            job.progress = 85
            job.result_summary = json.dumps({**backfill_summary, "stage": "正在计算 SVIX"})
            database.commit()
        results = calculate_svix(database, job.start_date, job.end_date, job.frequency)
        attempted_query = database.query(OptionSnapshot.timestamp).filter(OptionSnapshot.timestamp >= datetime.combine(job.start_date, datetime.min.time(), tzinfo=timezone.utc), OptionSnapshot.timestamp <= datetime.combine(job.end_date, datetime.max.time(), tzinfo=timezone.utc))
        if provider is not None:
            attempted_query = attempted_query.filter(OptionSnapshot.provider == provider.provider)
        attempted_dates = {timestamp.date() for (timestamp,) in attempted_query.all()}
        estimated_records = sum(1 for item in results if getattr(item, "estimated", False))
        skipped_records = max(0, len(attempted_dates) - len(results))
        job.status, job.progress, job.finished_at = "COMPLETED", 100, datetime.now(timezone.utc)
        job.result_summary = json.dumps({**backfill_summary, "records_calculated": len(results), "estimated_records": estimated_records, "skipped_records": skipped_records, "stage": "已完成"})
        database.commit()
        result = {"job_id": job_id, "status": job.status, "records_calculated": len(results)}
        _log("historical_calculation", "success", started, job_id=job_id, records_calculated=len(results))
        return result
    except Exception as exc:
        database.rollback()
        job = database.get(CalculationJob, job_id)
        if job is not None:
            job.status, job.progress, job.finished_at, job.error_message = "FAILED", 100, datetime.now(timezone.utc), _job_error(exc)
            database.commit()
        _log("historical_calculation", "failed", started, job_id=job_id, error=type(exc).__name__)
        raise
    finally:
        database.close()


@celery_app.task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_backoff_max=300, retry_kwargs={"max_retries": 3})
def calculate_latest_svix_task(self) -> dict[str, object]:
    """Strict calculation from the latest collected two-sided option snapshot."""
    database = SessionLocal()
    try:
        configured = database.query(ProviderCredential).filter_by(enabled=True).first()
        provider = configured.provider if configured else None
        latest_query = database.query(func.max(OptionSnapshot.timestamp))
        if provider:
            latest_query = latest_query.filter(OptionSnapshot.provider == provider)
        latest_timestamp = latest_query.scalar()
        if latest_timestamp is None:
            return {"records_calculated": 0, "reason": "no_option_snapshot"}
        calculation_date = latest_timestamp.date()
        results = calculate_svix(database, calculation_date, calculation_date, "daily", strict=True)
        return {"records_calculated": len(results), "calculation_date": calculation_date.isoformat(), "method": "strict"}
    finally:
        database.close()


@celery_app.task(bind=True, autoretry_for=(ConnectionError, TimeoutError), retry_backoff=True, retry_kwargs={"max_retries": 3})
def data_lifecycle_maintenance_task(self, force: bool = False) -> dict[str, object]:
    started = time.monotonic()
    database = SessionLocal()
    try:
        result = run_data_maintenance(database, force=force)
        _log("data_lifecycle_maintenance", str(result["status"]).lower(), started, result=result)
        return result
    finally:
        database.close()
