"""Safe retention and downsampling for time-series market data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json

from sqlalchemy.orm import Session

from app.database.models import DataMaintenanceRun, OptionSnapshot, SVIXDaily, SVIXHistory, SystemSettings

DEFAULT_POLICY = {
    "option_cleanup_enabled": True,
    "option_retention_days": 3,
    "svix_downsample_enabled": True,
    "detailed_retention_days": 7,
    "maintenance_time_utc": "03:30",
}


def load_lifecycle_policy(database: Session) -> dict[str, object]:
    values = dict(DEFAULT_POLICY)
    rows = database.query(SystemSettings).filter(SystemSettings.key.in_(values.keys())).all()
    for row in rows:
        values[row.key] = json.loads(row.value)
    return values


def _day_bounds(value: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(value, time.min, tzinfo=timezone.utc),
        datetime.combine(value, time.max, tzinfo=timezone.utc),
    )


def _upsert_daily(database: Session, calculation_date: date, rows: list[SVIXHistory]) -> None:
    ordered = sorted(rows, key=lambda row: row.timestamp)
    record = database.query(SVIXDaily).filter_by(date=calculation_date).first()
    if record is None:
        record = SVIXDaily(date=calculation_date)
        database.add(record)
    record.svix_open = ordered[0].svix
    record.svix_high = max(row.svix for row in ordered)
    record.svix_low = min(row.svix for row in ordered)
    record.svix_close = ordered[-1].svix
    record.core_close = ordered[-1].core_vol
    record.memory_close = ordered[-1].memory_vol
    record.ai_close = ordered[-1].ai_vol
    record.sample_count = len(ordered)
    record.min_calculation_quality = min(row.calculation_quality for row in ordered)


def _delete_ids_in_batches(database: Session, model, ids: list[int], batch_size: int) -> int:
    deleted = 0
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        deleted += database.query(model).filter(model.id.in_(batch)).delete(synchronize_session=False)
        database.commit()
    return deleted


def maintenance_due(database: Session, now: datetime) -> bool:
    policy = load_lifecycle_policy(database)
    hour, minute = (int(part) for part in str(policy["maintenance_time_utc"]).split(":"))
    scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    latest = database.query(DataMaintenanceRun).filter_by(status="COMPLETED").order_by(DataMaintenanceRun.finished_at.desc()).first()
    return now >= scheduled and not (latest and latest.finished_at and latest.finished_at.date() == now.date())


def run_data_maintenance(database: Session, *, now: datetime | None = None, force: bool = False, batch_size: int = 10_000) -> dict[str, object]:
    now = now or datetime.now(timezone.utc)
    if not force and not maintenance_due(database, now):
        return {"status": "SKIPPED", "reason": "not_due"}
    policy = load_lifecycle_policy(database)
    run = DataMaintenanceRun(status="RUNNING", started_at=now)
    database.add(run)
    database.commit()
    try:
        history_aggregated = daily_written = option_deleted = 0
        if bool(policy["svix_downsample_enabled"]):
            history_cutoff = now - timedelta(days=int(policy["detailed_retention_days"]))
            old_history = database.query(SVIXHistory).filter(SVIXHistory.timestamp < history_cutoff).order_by(SVIXHistory.timestamp.asc()).all()
            grouped: dict[date, list[SVIXHistory]] = defaultdict(list)
            for row in old_history:
                grouped[row.timestamp.date()].append(row)
            for calculation_date, rows in grouped.items():
                _upsert_daily(database, calculation_date, rows)
            database.commit()
            daily_written = len(grouped)
            history_aggregated = _delete_ids_in_batches(database, SVIXHistory, [row.id for row in old_history], batch_size)

        if bool(policy["option_cleanup_enabled"]):
            option_cutoff = now - timedelta(days=int(policy["option_retention_days"]))
            covered_dates = {timestamp.date() for (timestamp,) in database.query(SVIXHistory.timestamp).all()}
            covered_dates.update(value for (value,) in database.query(SVIXDaily.date).all())
            for calculation_date in covered_dates:
                start, end = _day_bounds(calculation_date)
                if end >= option_cutoff:
                    continue
                while True:
                    batch = [row_id for (row_id,) in database.query(OptionSnapshot.id).filter(OptionSnapshot.timestamp >= start, OptionSnapshot.timestamp <= end).limit(batch_size).all()]
                    if not batch:
                        break
                    option_deleted += database.query(OptionSnapshot).filter(OptionSnapshot.id.in_(batch)).delete(synchronize_session=False)
                    database.commit()

        run = database.get(DataMaintenanceRun, run.id)
        run.status = "COMPLETED"
        run.option_rows_deleted = option_deleted
        run.history_rows_aggregated = history_aggregated
        run.daily_rows_written = daily_written
        run.finished_at = datetime.now(timezone.utc)
        database.commit()
        return {"status": run.status, "option_rows_deleted": option_deleted, "history_rows_aggregated": history_aggregated, "daily_rows_written": daily_written}
    except Exception:
        database.rollback()
        failed = database.get(DataMaintenanceRun, run.id)
        if failed is not None:
            failed.status = "FAILED"
            failed.finished_at = datetime.now(timezone.utc)
            failed.error_message = "Data maintenance failed"
            database.commit()
        raise
