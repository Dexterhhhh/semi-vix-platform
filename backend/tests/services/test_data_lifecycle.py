from datetime import datetime, timedelta, timezone

from app.database.database import Base, SessionLocal, engine
from app.database.models import DataMaintenanceRun, OptionSnapshot, SVIXDaily, SVIXHistory
from app.services.data_lifecycle import run_data_maintenance


def _option(timestamp: datetime, contract_id: str, provider: str = "IBKR") -> OptionSnapshot:
    return OptionSnapshot(timestamp=timestamp, provider=provider, contract_id=contract_id, symbol="SOXX", expiry=timestamp + timedelta(days=30), strike=500, option_type="C", bid=1, ask=2)


def test_maintenance_downsamples_then_deletes_only_covered_old_options() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    now = datetime(2026, 7, 12, 4, 0, tzinfo=timezone.utc)
    old = now - timedelta(days=10)
    uncovered = now - timedelta(days=12)
    recent = now - timedelta(days=1)
    try:
        database.add_all([
            SVIXHistory(timestamp=old, svix=30, core_vol=29, memory_vol=35, ai_vol=31, calculation_quality=.9, source_feed="ibkr:smart"),
            _option(old, "covered"),
            _option(old, "other-provider", "FUTU"),
            _option(uncovered, "uncovered"),
            _option(recent, "recent"),
        ])
        database.commit()
        result = run_data_maintenance(database, now=now, force=True, batch_size=1)
        assert result == {"status": "COMPLETED", "option_rows_deleted": 1, "history_rows_aggregated": 1, "daily_rows_written": 1}
        daily = database.query(SVIXDaily).one()
        assert daily.svix_open == daily.svix_close == 30
        assert daily.sample_count == 1
        assert {row.contract_id for row in database.query(OptionSnapshot).all()} == {"other-provider", "uncovered", "recent"}
        assert database.query(DataMaintenanceRun).one().status == "COMPLETED"
    finally:
        database.close()


def test_downsampling_merges_late_rows_without_overwriting_existing_ohlc() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    now = datetime(2026, 7, 12, 4, 0, tzinfo=timezone.utc)
    day = (now - timedelta(days=10)).date()
    at_15 = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=15)
    at_18 = at_15 + timedelta(hours=3)
    at_17 = at_15 + timedelta(hours=2)
    try:
        database.add_all([
            SVIXHistory(timestamp=at_15, svix=10, core_vol=10, memory_vol=10, ai_vol=10, calculation_quality=.9, source_feed="ibkr:smart"),
            SVIXHistory(timestamp=at_18, svix=30, core_vol=30, memory_vol=30, ai_vol=30, calculation_quality=.8, source_feed="ibkr:smart"),
        ])
        database.commit()
        run_data_maintenance(database, now=now, force=True)
        database.add(SVIXHistory(timestamp=at_17, svix=20, core_vol=20, memory_vol=20, ai_vol=20, calculation_quality=.85, source_feed="ibkr:smart"))
        database.commit()
        run_data_maintenance(database, now=now + timedelta(hours=1), force=True)
        daily = database.query(SVIXDaily).one()
        assert (daily.svix_open, daily.svix_high, daily.svix_low, daily.svix_close) == (10, 30, 10, 30)
        assert daily.sample_count == 3
    finally:
        database.close()
