"""Historical SVIX calculation service built on persisted market snapshots."""

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
from app.services.custom_index import calculate_custom_index, custom_symbols, enabled_definitions, save_custom_result

logger = logging.getLogger(__name__)
Frequency = Literal["daily", "weekly"]


def _bounds(value: date, end: bool = False) -> datetime:
    return datetime.combine(value, time.max if end else time.min, tzinfo=timezone.utc)


def _snapshot_to_quote(snapshot: OptionSnapshot) -> OptionQuote:
    expiry = snapshot.expiry
    # Older Alpaca snapshots were persisted at 00:00 UTC on expiry day.  OCC
    # equity options remain tradable through the US market session, so use a
    # stable post-close UTC timestamp without rewriting existing rows.
    if snapshot.provider == "ALPACA":
        expiry = datetime.combine(expiry.date(), time(21, 0), tzinfo=timezone.utc)
    return OptionQuote(contract_id=snapshot.contract_id, symbol=snapshot.symbol, expiry=expiry, strike=snapshot.strike, option_type=snapshot.option_type, timestamp=snapshot.timestamp, bid=snapshot.bid, ask=snapshot.ask, last=snapshot.last, volume=snapshot.volume, open_interest=snapshot.open_interest, implied_volatility=snapshot.implied_volatility, provider=snapshot.provider, delayed=snapshot.delayed)


class HistoricalSVIXCalculator:
    def __init__(self, database: Session, engine: SVIXEngine | None = None):
        self.database = database
        self.engine = engine or SVIXEngine()
        self.options = OptionRepository(database)
        self.stocks = QuoteRepository(database)
        self.history = SVIXRepository(database)

    def _provider(self) -> tuple[str, str]:
        configured = self.database.query(ProviderCredential).filter_by(enabled=True).first()
        provider = configured.provider if configured else get_settings().data_provider
        feed = configured.data_feed if configured and configured.data_feed else provider.lower()
        return provider, f"{provider.lower()}:{feed.lower()}"

    def _available_dates(self, provider: str, start: date, end: date, frequency: Frequency) -> list[date]:
        rows = self.database.query(OptionSnapshot.timestamp).filter(OptionSnapshot.provider == provider, OptionSnapshot.timestamp >= _bounds(start), OptionSnapshot.timestamp <= _bounds(end, end=True)).order_by(OptionSnapshot.timestamp.asc()).all()
        dates = sorted({timestamp.date() for (timestamp,) in rows})
        return dates if frequency == "daily" else [item for item in dates if item.weekday() == 4]

    def _symbols(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*DEFAULT_UNIVERSE, *custom_symbols(self.database))))

    def _day_quotes(self, provider: str, calculation_date: date, symbols: tuple[str, ...]) -> dict[str, list[OptionQuote]]:
        grouped: dict[str, list[OptionQuote]] = {}
        for symbol in symbols:
            snapshots = self.options.by_time_range(symbol, provider, _bounds(calculation_date), _bounds(calculation_date, end=True))
            latest_per_contract: dict[str, OptionSnapshot] = {}
            for snapshot in snapshots:
                if snapshot.contract_id not in latest_per_contract or snapshot.timestamp > latest_per_contract[snapshot.contract_id].timestamp:
                    latest_per_contract[snapshot.contract_id] = snapshot
            if latest_per_contract:
                grouped[symbol] = [_snapshot_to_quote(snapshot) for snapshot in latest_per_contract.values()]
        return grouped

    def _historical_market_data(self, provider: str, as_of: date, symbols: tuple[str, ...]) -> tuple[dict[str, list[float]], dict[str, float]]:
        start = _bounds(as_of - timedelta(days=400))
        end = _bounds(as_of, end=True)
        returns: dict[str, list[float]] = {}
        spots: dict[str, float] = {}
        for symbol in symbols:
            latest_by_day = {}
            for snapshot in self.stocks.by_time_range(symbol, provider, start, end):
                if snapshot.price is not None:
                    latest_by_day[snapshot.timestamp.date()] = snapshot
            prices = [latest_by_day[item].price for item in sorted(latest_by_day)]
            if len(prices) >= 253:
                returns[symbol] = calculate_returns(prices)
                spots[symbol] = prices[-1]
        return returns, spots

    def calculate_svix(self, start_date: date, end_date: date, frequency: Frequency = "daily", *, strict: bool = False) -> list[SVIXResult]:
        if end_date < start_date:
            raise ValueError("end_date must not be before start_date")
        provider, source_feed = self._provider()
        results: list[SVIXResult] = []
        symbols = self._symbols()
        custom_definitions = enabled_definitions(self.database)
        for calculation_date in self._available_dates(provider, start_date, end_date, frequency):
            quotes = self._day_quotes(provider, calculation_date, symbols)
            returns, spots = self._historical_market_data(provider, calculation_date, symbols)
            available = set(quotes) & set(returns)
            quotes = {symbol: chain for symbol, chain in quotes.items() if symbol in available}
            returns = {symbol: values for symbol, values in returns.items() if symbol in available}
            spots = {symbol: value for symbol, value in spots.items() if symbol in available}
            if not quotes:
                logger.warning("Skipping %s: incomplete option snapshot universe", calculation_date.isoformat())
                continue
            valuation_time = max(quote.timestamp for chain in quotes.values() for quote in chain)
            approximate = False if strict else any(quote.delayed for chain in quotes.values() for quote in chain)
            try:
                result = self.engine.calculate(quotes, returns, valuation_time, underlying_prices=spots, approximate=approximate, source_feed=source_feed)
                self.history.save(result)
                results.append(result)
            except (SVIXError, ValueError) as exc:
                logger.warning("Skipping standard SVIX on %s: %s", calculation_date.isoformat(), exc)
            for definition in custom_definitions:
                try:
                    custom_result = calculate_custom_index(definition, quotes, returns, valuation_time, engine=self.engine, underlying_prices=spots, approximate=approximate, source_feed=source_feed)
                    save_custom_result(self.database, definition, custom_result)
                except (SVIXError, ValueError) as exc:
                    logger.warning("Skipping custom index %s on %s: %s", definition.index.id, calculation_date.isoformat(), exc)
        self.database.commit()
        return results


def calculate_svix(database: Session, start_date: date, end_date: date, frequency: Frequency = "daily", *, strict: bool = False) -> list[SVIXResult]:
    """Service-compatible entry point for later queue/scheduler integration."""
    return HistoricalSVIXCalculator(database).calculate_svix(start_date, end_date, frequency, strict=strict)
