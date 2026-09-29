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
    monkeypatch.setattr("app.scheduler.tasks.refresh_market_data", lambda: {"batch_id": "test-batch", "stock_quotes_saved": 6, "option_quotes_saved": 120, "symbols_succeeded": 6, "symbols_failed": 0})
    dispatched: list[str] = []
    monkeypatch.setattr("app.scheduler.tasks.calculate_latest_svix_task", lambda batch_id: dispatched.append(batch_id))
    database = SessionLocal()
    database.add(SystemSettings(key="refresh_frequency_minutes", value=json.dumps(30)))
    database.add(SystemSettings(key="intraday_refresh_seconds", value=json.dumps(60)))
    database.commit()
    database.close()

    first = collect_market_data_task()
    second = collect_market_data_task()
    assert first["status"] == "COMPLETED"
    assert first["interval_seconds"] == 60
    assert second["reason"] == "interval_not_due"
    assert dispatched == ["test-batch"]
    database = SessionLocal()
    try:
        saved = database.query(MarketCollectionRun).one()
        assert saved.status == "COMPLETED"
        assert saved.option_quotes_saved == 120
        assert saved.interval_seconds == 60
    finally:
        database.close()


def test_collection_does_not_run_when_market_is_closed(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    status = MarketStatus("CLOSED", False, date.today(), now - timedelta(hours=8), now - timedelta(hours=1), now - timedelta(minutes=30), now + timedelta(days=1))
    monkeypatch.setattr("app.scheduler.tasks.market_status", lambda value=None: status)
    called: list[bool] = []
    monkeypatch.setattr("app.scheduler.tasks.refresh_market_data", lambda: called.append(True))
    result = collect_market_data_task()
    assert result["reason"] == "market_closed"
    assert called == []


def test_empty_collection_is_throttled_and_honors_retry_after(monkeypatch) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)
    status = MarketStatus("OPEN", True, date.today(), now - timedelta(hours=1), now + timedelta(hours=5), now + timedelta(hours=5, minutes=30), None)
    monkeypatch.setattr("app.scheduler.tasks.market_status", lambda value=None: status)
    calls: list[bool] = []

    def empty_refresh():
        calls.append(True)
        return {"batch_id": "empty-batch", "stock_quotes_saved": 0, "option_quotes_saved": 0, "symbols_succeeded": 0, "symbols_failed": 1, "retry_after_seconds": 120}

    monkeypatch.setattr("app.scheduler.tasks.refresh_market_data", empty_refresh)
    first = collect_market_data_task()
    second = collect_market_data_task()
    assert first["status"] == "NO_VALID_DATA"
    assert second["reason"] == "interval_not_due"
    assert calls == [True]
    with SessionLocal() as database:
        run = database.query(MarketCollectionRun).one()
        assert run.retry_after_seconds == 120
