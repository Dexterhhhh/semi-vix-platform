from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.models import OptionQuote
from app.database.models import OptionSnapshot


class OptionRepository:
    """Persistence boundary for normalized option quote snapshots."""

    def __init__(self, database: Session):
        self.database = database

    @staticmethod
    def _snapshot(quote: OptionQuote) -> OptionSnapshot:
        return OptionSnapshot(timestamp=quote.timestamp, provider=quote.provider, contract_id=quote.contract_id, symbol=quote.symbol, expiry=quote.expiry, strike=quote.strike, option_type=quote.option_type, bid=quote.bid, ask=quote.ask, last=quote.last, volume=quote.volume, open_interest=quote.open_interest, implied_volatility=quote.implied_volatility, delayed=quote.delayed, feed=quote.feed, price_type=quote.price_type, received_at=quote.received_at, batch_id=quote.batch_id)

    def save(self, quote: OptionQuote) -> OptionSnapshot:
        snapshot = self._snapshot(quote)
        self.database.add(snapshot)
        return snapshot

    def save_many(self, quotes: list[OptionQuote]) -> list[OptionSnapshot]:
        snapshots = [self._snapshot(quote) for quote in quotes]
        self.database.add_all(snapshots)
        return snapshots

    def latest_chain(self, symbol: str, provider: str) -> list[OptionSnapshot]:
        timestamp = self.database.query(func.max(OptionSnapshot.timestamp)).filter_by(symbol=symbol.upper(), provider=provider.upper()).scalar()
        if timestamp is None:
            return []
        return self.database.query(OptionSnapshot).filter_by(symbol=symbol.upper(), provider=provider.upper(), timestamp=timestamp).order_by(OptionSnapshot.expiry, OptionSnapshot.strike, OptionSnapshot.option_type).all()

    def available_expirations(self, symbol: str, provider: str) -> list[datetime]:
        return [value[0] for value in self.database.query(OptionSnapshot.expiry).filter_by(symbol=symbol.upper(), provider=provider.upper()).distinct().order_by(OptionSnapshot.expiry).all()]

    def by_time_range(self, symbol: str, provider: str, start: datetime, end: datetime) -> list[OptionSnapshot]:
        return self.database.query(OptionSnapshot).filter(OptionSnapshot.symbol == symbol.upper(), OptionSnapshot.provider == provider.upper(), OptionSnapshot.timestamp >= start, OptionSnapshot.timestamp <= end).order_by(OptionSnapshot.timestamp.asc(), OptionSnapshot.expiry, OptionSnapshot.strike).all()
