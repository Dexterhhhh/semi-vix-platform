from datetime import date, datetime, timezone

from app.scheduler.market_hours import market_status, session_bounds


def test_regular_session_and_post_close_delay_window() -> None:
    during = market_status(datetime(2026, 7, 6, 15, 0, tzinfo=timezone.utc))
    assert during.state == "OPEN"
    assert during.is_collection_window is True
    delayed = market_status(datetime(2026, 7, 6, 20, 15, tzinfo=timezone.utc))
    assert delayed.state == "POST_CLOSE_DELAY"
    assert delayed.is_collection_window is True
    closed = market_status(datetime(2026, 7, 6, 20, 31, tzinfo=timezone.utc))
    assert closed.state == "CLOSED"
    assert closed.is_collection_window is False


def test_weekend_is_closed_and_early_close_gets_its_own_delay() -> None:
    weekend = market_status(datetime(2026, 7, 12, 16, 0, tzinfo=timezone.utc))
    assert weekend.state == "CLOSED"
    assert weekend.session_date == date(2026, 7, 10)
    bounds = session_bounds(date(2026, 11, 27))
    assert bounds is not None
    opened, collection_end = bounds
    assert opened.hour == 14 and opened.minute == 30
    assert collection_end.hour == 18 and collection_end.minute == 30
