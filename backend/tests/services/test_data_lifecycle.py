from datetime import datetime, timedelta, timezone

from app.database.database import Base, SessionLocal, engine
from app.database.models import DataMaintenanceRun, OptionSnapshot, SVIXDaily, SVIXHistory
from app.services.data_lifecycle import run_data_maintenance


def _option(timestamp: datetime, contract_id: str) -> OptionSnapshot:
    return OptionSnapshot(timestamp=timestamp, provider="IBKR", contract_id=contract_id, symbol="SOXX", expiry=timestamp + timedelta(days=30), strike=500, option_type="C", bid=1, ask=2)


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
            SVIXHistory(timestamp=old, svix=30, core_vol=29, memory_vol=35, ai_vol=31, calculation_quality=.9),
            _option(old, "covered"),
            _option(uncovered, "uncovered"),
            _option(recent, "recent"),
        ])
        database.commit()
        result = run_data_maintenance(database, now=now, force=True, batch_size=1)
        assert result == {"status": "COMPLETED", "option_rows_deleted": 1, "history_rows_aggregated": 1, "daily_rows_written": 1}
        daily = database.query(SVIXDaily).one()
        assert daily.svix_open == daily.svix_close == 30
        assert daily.sample_count == 1
        assert {row.contract_id for row in database.query(OptionSnapshot).all()} == {"uncovered", "recent"}
        assert database.query(DataMaintenanceRun).one().status == "COMPLETED"
    finally:
        database.close()
