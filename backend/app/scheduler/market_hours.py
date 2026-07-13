"""NYSE regular-session clock with a bounded post-close collection window."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

NEW_YORK = ZoneInfo("America/New_York")
POST_CLOSE_DELAY = timedelta(minutes=30)


@dataclass(frozen=True)
class MarketStatus:
    state: str
    is_collection_window: bool
    session_date: date | None
    market_open: datetime | None
    market_close: datetime | None
    collection_end: datetime | None
    next_open: datetime | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@lru_cache(maxsize=1)
def _calendar():
    return mcal.get_calendar("NYSE")


def _utc(value) -> datetime:
    converted = value.to_pydatetime()
    return converted.astimezone(timezone.utc)


def market_status(now: datetime | None = None) -> MarketStatus:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    local_date = now.astimezone(NEW_YORK).date()
    schedule = _calendar().schedule(start_date=local_date - timedelta(days=10), end_date=local_date + timedelta(days=14))
    sessions: list[tuple[date, datetime, datetime]] = [
        (index.date(), _utc(row["market_open"]), _utc(row["market_close"]))
        for index, row in schedule.iterrows()
    ]
    current = next((item for item in sessions if item[0] == local_date), None)
    previous = next((item for item in reversed(sessions) if item[0] <= local_date), None)
    next_open = next((opened for _, opened, _ in sessions if opened > now), None)
    display = current or previous
    if current is None:
        return MarketStatus("CLOSED", False, display[0] if display else None, display[1] if display else None, display[2] if display else None, display[2] + POST_CLOSE_DELAY if display else None, next_open)
    session_date, opened, closed = current
    collection_end = closed + POST_CLOSE_DELAY
    if now < opened:
        state = "PRE_MARKET"
    elif now <= closed:
        state = "OPEN"
    elif now <= collection_end:
        state = "POST_CLOSE_DELAY"
    else:
        state = "CLOSED"
    return MarketStatus(state, state in {"OPEN", "POST_CLOSE_DELAY"}, session_date, opened, closed, collection_end, next_open)


def session_bounds(session_date: date) -> tuple[datetime, datetime] | None:
    schedule = _calendar().schedule(start_date=session_date, end_date=session_date)
    if schedule.empty:
        return None
    row = schedule.iloc[0]
    return _utc(row["market_open"]), _utc(row["market_close"]) + POST_CLOSE_DELAY
