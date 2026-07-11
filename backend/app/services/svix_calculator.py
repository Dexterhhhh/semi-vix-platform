"""Historical SVIX calculation service built solely on persisted Phase 2 data."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Literal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.models import OptionQuote
from app.data.storage.option_repository import OptionRepository
from app.data.storage.quote_repository import QuoteRepository
from app.database.models import OptionSnapshot, ProviderCredential
from app.svix.correlation import calculate_returns
from app.svix.engine import SVIXEngine
from app.svix.exceptions import SVIXError
from app.svix.models import SVIXResult
from app.svix.svix_repository import SVIXRepository
from app.svix.universe import DEFAULT_UNIVERSE

logger = logging.getLogger(__name__)
Frequency = Literal["daily", "weekly"]


def _bounds(value: date, end: bool = False) -> datetime:
    return datetime.combine(value, time.max if end else time.min, tzinfo=timezone.utc)


def _snapshot_to_quote(snapshot: OptionSnapshot) -> OptionQuote:
    return OptionQuote(contract_id=snapshot.contract_id, symbol=snapshot.symbol, expiry=snapshot.expiry, strike=snapshot.strike, option_type=snapshot.option_type, timestamp=snapshot.timestamp, bid=snapshot.bid, ask=snapshot.ask, last=snapshot.last, volume=snapshot.volume, open_interest=snapshot.open_interest, implied_volatility=snapshot.implied_volatility, provider=snapshot.provider, delayed=snapshot.delayed)


class HistoricalSVIXCalculator:
    def __init__(self, database: Session, engine: SVIXEngine | None = None):
        self.database = database
        self.engine = engine or SVIXEngine()
        self.options = OptionRepository(database)
        self.stocks = QuoteRepository(database)
        self.history = SVIXRepository(database)

    def _provider(self) -> str:
        configured = self.database.query(ProviderCredential).filter_by(enabled=True).first()
        return configured.provider if configured else get_settings().data_provider

    def _available_dates(self, provider: str, start: date, end: date, frequency: Frequency) -> list[date]:
        rows = self.database.query(OptionSnapshot.timestamp).filter(OptionSnapshot.provider == provider, OptionSnapshot.timestamp >= _bounds(start), OptionSnapshot.timestamp <= _bounds(end, end=True)).order_by(OptionSnapshot.timestamp.asc()).all()
        dates = sorted({timestamp.date() for (timestamp,) in rows})
        return dates if frequency == "daily" else [item for item in dates if item.weekday() == 4]

    def _day_quotes(self, provider: str, calculation_date: date) -> dict[str, list[OptionQuote]]:
        grouped: dict[str, list[OptionQuote]] = {}
        for symbol in DEFAULT_UNIVERSE:
            snapshots = self.options.by_time_range(symbol, provider, _bounds(calculation_date), _bounds(calculation_date, end=True))
            latest_per_contract: dict[str, OptionSnapshot] = {}
            for snapshot in snapshots:
                if snapshot.contract_id not in latest_per_contract or snapshot.timestamp > latest_per_contract[snapshot.contract_id].timestamp:
                    latest_per_contract[snapshot.contract_id] = snapshot
            if not latest_per_contract:
                return {}
            grouped[symbol] = [_snapshot_to_quote(snapshot) for snapshot in latest_per_contract.values()]
        return grouped

    def _historical_returns(self, provider: str, as_of: date) -> dict[str, list[float]]:
        start = _bounds(as_of - timedelta(days=400))
        end = _bounds(as_of, end=True)
        returns: dict[str, list[float]] = {}
        for symbol in DEFAULT_UNIVERSE:
            latest_by_day = {}
            for snapshot in self.stocks.by_time_range(symbol, provider, start, end):
                if snapshot.price is not None:
                    latest_by_day[snapshot.timestamp.date()] = snapshot
            prices = [latest_by_day[item].price for item in sorted(latest_by_day)]
            returns[symbol] = calculate_returns(prices)
        return returns

    def calculate_svix(self, start_date: date, end_date: date, frequency: Frequency = "daily") -> list[SVIXResult]:
        if end_date < start_date:
            raise ValueError("end_date must not be before start_date")
        provider = self._provider()
        results: list[SVIXResult] = []
        for calculation_date in self._available_dates(provider, start_date, end_date, frequency):
            quotes = self._day_quotes(provider, calculation_date)
            if not quotes:
                logger.warning("Skipping %s: incomplete option snapshot universe", calculation_date.isoformat())
                continue
            valuation_time = max(quote.timestamp for chain in quotes.values() for quote in chain)
            try:
                result = self.engine.calculate(quotes, self._historical_returns(provider, calculation_date), valuation_time)
            except SVIXError as exc:
                logger.warning("Skipping %s: %s", calculation_date.isoformat(), exc)
                continue
            self.history.save(result)
            results.append(result)
        self.database.commit()
        return results


def calculate_svix(database: Session, start_date: date, end_date: date, frequency: Frequency = "daily") -> list[SVIXResult]:
    """Service-compatible entry point for later queue/scheduler integration."""
    return HistoricalSVIXCalculator(database).calculate_svix(start_date, end_date, frequency)
