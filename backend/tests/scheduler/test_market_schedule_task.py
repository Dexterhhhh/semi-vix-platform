from datetime import date, datetime, timedelta, timezone
import json

from app.database.database import Base, SessionLocal, engine
from app.database.models import MarketCollectionRun, SystemSettings
from app.scheduler.market_hours import MarketStatus
from app.scheduler.tasks import collect_market_data_task


def test_collection_uses_database_interval_and_skips_until_due(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session_date = date.today()
    now = datetime.now(timezone.utc)
    status = MarketStatus("OPEN", True, session_date, now - timedelta(hours=1), now + timedelta(hours=5), now + timedelta(hours=5, minutes=30), None)
    monkeypatch.setattr("app.scheduler.tasks.market_status", lambda value=None: status)
    monkeypatch.setattr("app.scheduler.tasks.refresh_market_data", lambda: {"stock_quotes_saved": 6, "option_quotes_saved": 120, "symbols_succeeded": 6, "symbols_failed": 0})
    dispatched: list[bool] = []
    monkeypatch.setattr("app.scheduler.tasks.calculate_latest_svix_task.delay", lambda: dispatched.append(True))
    database = SessionLocal()
    database.add(SystemSettings(key="refresh_frequency_minutes", value=json.dumps(30)))
    database.add(SystemSettings(key="intraday_refresh_seconds", value=json.dumps(30)))
    database.commit()
    database.close()

    first = collect_market_data_task.run()
    second = collect_market_data_task.run()
    assert first["status"] == "COMPLETED"
    assert first["interval_seconds"] == 30
    assert second["reason"] == "interval_not_due"
    assert dispatched == [True]
    database = SessionLocal()
    try:
        saved = database.query(MarketCollectionRun).one()
        assert saved.status == "COMPLETED"
        assert saved.option_quotes_saved == 120
        assert saved.interval_seconds == 30
    finally:
        database.close()


def test_collection_does_not_run_when_market_is_closed(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    status = MarketStatus("CLOSED", False, date.today(), now - timedelta(hours=8), now - timedelta(hours=1), now - timedelta(minutes=30), now + timedelta(days=1))
    monkeypatch.setattr("app.scheduler.tasks.market_status", lambda value=None: status)
    called: list[bool] = []
    monkeypatch.setattr("app.scheduler.tasks.refresh_market_data", lambda: called.append(True))
    result = collect_market_data_task.run()
    assert result["reason"] == "market_closed"
    assert called == []
