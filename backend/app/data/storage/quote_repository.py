from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.data.models import StockQuote
from app.database.models import StockSnapshot


class QuoteRepository:
    """Persistence boundary for normalized underlying quotes.

    The caller owns commit/rollback so a collector can persist one symbol in a
    savepoint without accidentally committing another symbol's data.
    """

    def __init__(self, database: Session):
        self.database = database

    def save(self, quote: StockQuote) -> StockSnapshot:
        snapshot = StockSnapshot(timestamp=quote.timestamp, provider=quote.provider, symbol=quote.symbol, price=quote.price, bid=quote.bid, ask=quote.ask, volume=quote.volume, delayed=quote.delayed, feed=quote.feed, price_type=quote.price_type, received_at=quote.received_at, batch_id=quote.batch_id)
        self.database.add(snapshot)
        return snapshot

    def save_many(self, quotes: list[StockQuote]) -> list[StockSnapshot]:
        snapshots = [StockSnapshot(timestamp=quote.timestamp, provider=quote.provider, symbol=quote.symbol, price=quote.price, bid=quote.bid, ask=quote.ask, volume=quote.volume, delayed=quote.delayed, feed=quote.feed, price_type=quote.price_type, received_at=quote.received_at, batch_id=quote.batch_id) for quote in quotes]
        self.database.add_all(snapshots)
        return snapshots

    def latest(self, symbol: str, provider: str) -> StockSnapshot | None:
        return self.database.query(StockSnapshot).filter_by(symbol=symbol.upper(), provider=provider.upper()).order_by(StockSnapshot.timestamp.desc(), StockSnapshot.id.desc()).first()

    def by_time_range(self, symbol: str, provider: str, start: datetime, end: datetime) -> list[StockSnapshot]:
        return self.database.query(StockSnapshot).filter(StockSnapshot.symbol == symbol.upper(), StockSnapshot.provider == provider.upper(), StockSnapshot.timestamp >= start, StockSnapshot.timestamp <= end).order_by(StockSnapshot.timestamp.asc()).all()
