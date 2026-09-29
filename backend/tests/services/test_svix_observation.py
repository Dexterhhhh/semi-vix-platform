"""Regression tests for batch isolation, partial coverage and bounded reuse."""

from datetime import date, datetime, timedelta, timezone
import json

from app.database.database import Base, SessionLocal, engine
from app.database.models import MarketCollectionRun, OptionSnapshot, SVIXAssetObservation, SVIXCorrelationCache, SVIXObservation
from app.services.svix_observation import calculate_observation
from app.services.observation_replay import replay_observations

SESSION = date(2026, 9, 22)
AT = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)


def add_batch(database, batch_id: str, at: datetime, symbols: tuple[str, ...], quote_at: datetime | None = None, expiry: datetime | None = None) -> None:
    database.add(MarketCollectionRun(session_date=SESSION, status="COMPLETED", interval_minutes=1, interval_seconds=60, started_at=at - timedelta(seconds=30), finished_at=at, batch_id=batch_id))
    expiry = expiry or datetime(2026, 10, 22, 21, tzinfo=timezone.utc)
    for symbol in symbols:
        for strike in (90., 100., 110.):
            for right in ("C", "P"):
                database.add(OptionSnapshot(timestamp=quote_at or at - timedelta(minutes=1), provider="ALPACA", contract_id=f"ALPACA:{symbol}:{expiry.date()}:{strike}:{right}", symbol=symbol, expiry=expiry, strike=strike, option_type=right, bid=1.0 if strike != 100 else 2.0, ask=1.2 if strike != 100 else 2.2, price_type="indicative_quote", feed="indicative", delayed=True, received_at=at, batch_id=batch_id))
    database.commit()


def add_matrix(database) -> None:
    assets = ["AMD", "AVGO", "MU", "NVDA", "SKHY", "SOXX"]
    matrix = [[1.0 if i == j else 0.3 for j in range(len(assets))] for i in range(len(assets))]
    database.add(SVIXCorrelationCache(provider="ALPACA", as_of=date(2026, 9, 21), available_at=AT - timedelta(days=1), assets=json.dumps(assets), matrix=json.dumps(matrix)))
    database.commit()


def test_missing_skyh_uses_partial_coverage_and_only_its_batch() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        add_matrix(database)
        add_batch(database, "first", AT, ("SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO"))
        add_batch(database, "second", AT + timedelta(minutes=2), ("SOXX", "MU", "NVDA", "AMD", "AVGO"))
        result = calculate_observation(database, "second")
        assert result is not None
        assert result.svix is not None
        assert result.core is not None and result.memory is not None and result.ai is not None
        assert abs(result.coverage - 0.85) < 1e-9
        details = json.loads(result.details)
        assert details["assets"]["SKHY"]["status"] == "NO_BATCH_QUOTES"
        assert details["component_counts"]["memory"] == "1/2"
        assert database.query(SVIXObservation).count() == 1
        assert calculate_observation(database, "second").id == result.id


def test_soxx_failure_keeps_other_components_and_no_full_value() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        add_matrix(database)
        add_batch(database, "partial", AT, ("MU", "NVDA"))
        result = calculate_observation(database, "partial")
        assert result is not None
        assert result.core is None and result.svix is None
        assert result.memory is not None and result.ai is not None
        assert json.loads(result.details)["reasons"]["svix"] == "SOXX_UNAVAILABLE"


def test_unchanged_quotes_do_not_make_new_market_point_and_cache_expires() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        add_batch(database, "one", AT, ("SOXX",))
        assert calculate_observation(database, "one") is not None
        add_batch(database, "two", AT + timedelta(minutes=2), ("SOXX",), quote_at=AT - timedelta(minutes=1))
        assert calculate_observation(database, "two") is None
        cached = database.query(SVIXAssetObservation).filter_by(batch_id="two", symbol="SOXX").one()
        assert cached.status == "CACHED"
        add_batch(database, "three", AT + timedelta(minutes=11), ("SOXX",), quote_at=AT - timedelta(minutes=1))
        assert calculate_observation(database, "three") is None
        expired = database.query(SVIXAssetObservation).filter_by(batch_id="three", symbol="SOXX").one()
        assert expired.status != "CACHED"
        assert database.query(SVIXObservation).count() == 1


def test_cache_contributes_only_within_both_time_limits() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        add_matrix(database)
        add_batch(database, "origin", AT, ("SOXX", "MU", "NVDA"))
        assert calculate_observation(database, "origin") is not None
        add_batch(database, "refresh", AT + timedelta(minutes=3), ("SOXX",))
        result = calculate_observation(database, "refresh")
        assert result is not None and result.svix is not None
        assert abs(result.coverage - 0.75) < 1e-9
        assert abs(result.cached_coverage - 0.25) < 1e-9
        assert result.status == "CACHED"
        details = json.loads(result.details)
        assert details["assets"]["MU"]["source_batch_id"] == "origin"


def test_quote_age_and_single_expiry_boundaries() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        add_batch(database, "five", AT, ("SOXX",), quote_at=AT - timedelta(minutes=5))
        at_five = calculate_observation(database, "five")
        assert at_five is not None
        assert json.loads(at_five.details)["assets"]["SOXX"]["quote_age_minutes"] == 5
        add_batch(database, "fifteen", AT + timedelta(minutes=1), ("MU",), quote_at=AT - timedelta(minutes=14))
        assert calculate_observation(database, "fifteen") is not None
        add_batch(database, "too-old", AT + timedelta(minutes=2), ("NVDA",), quote_at=AT - timedelta(minutes=14, seconds=1))
        assert calculate_observation(database, "too-old") is None
        add_batch(database, "too-far-expiry", AT + timedelta(minutes=3), ("AMD",), expiry=AT + timedelta(days=38))
        assert calculate_observation(database, "too-far-expiry") is None


def test_replay_is_dry_run_by_default_and_idempotent_when_written() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        add_batch(database, "replay", AT, ("SOXX",))
        planned = replay_observations(database, SESSION, SESSION)
        assert planned[0]["status"] == "READY"
        assert database.query(SVIXObservation).count() == 0
        assert replay_observations(database, SESSION, SESSION, write=True)[0]["status"] == "OBSERVED"
        assert replay_observations(database, SESSION, SESSION, write=True)[0]["status"] == "OBSERVED"
        assert database.query(SVIXObservation).count() == 1


def test_replay_cannot_use_a_correlation_matrix_created_later() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as database:
        assets = ["MU", "SOXX"]
        database.add(SVIXCorrelationCache(provider="ALPACA", as_of=date(2026, 9, 21), available_at=AT + timedelta(days=1), assets=json.dumps(assets), matrix=json.dumps([[1, .3], [.3, 1]])))
        database.commit()
        add_batch(database, "no-lookahead", AT, ("SOXX", "MU", "NVDA"))
        result = calculate_observation(database, "no-lookahead")
        assert result is not None
        assert result.svix is None
        assert result.core is not None and result.memory is not None and result.ai is not None
        assert json.loads(result.details)["reasons"]["svix"] == "INSUFFICIENT_DAILY_HISTORY"
