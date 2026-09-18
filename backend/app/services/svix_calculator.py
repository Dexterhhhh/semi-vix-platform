"""Historical SVIX calculation service built on persisted market snapshots."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Literal, Mapping

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
    return OptionQuote(contract_id=snapshot.contract_id, symbol=snapshot.symbol, expiry=expiry, strike=snapshot.strike, option_type=snapshot.option_type, timestamp=snapshot.timestamp, bid=snapshot.bid, ask=snapshot.ask, last=snapshot.last, volume=snapshot.volume, open_interest=snapshot.open_interest, implied_volatility=snapshot.implied_volatility, provider=snapshot.provider, delayed=snapshot.delayed, feed=snapshot.feed, price_type=snapshot.price_type, received_at=snapshot.received_at, batch_id=snapshot.batch_id)


def _aligned_returns(
    prices_by_symbol: Mapping[str, Mapping[date, float]], symbols: set[str]
) -> dict[str, list[float]]:
    usable = {symbol for symbol in symbols if len(prices_by_symbol.get(symbol, {})) >= 253}
    if not usable:
        return {}
    common_dates = set.intersection(*(set(prices_by_symbol[symbol]) for symbol in usable))
    ordered_dates = sorted(common_dates)
    if len(ordered_dates) < 253:
        return {}
    return {
        symbol: calculate_returns([prices_by_symbol[symbol][day] for day in ordered_dates])
        for symbol in usable
    }


def _quote_identity(quotes: Mapping[str, list[OptionQuote]]) -> tuple[str, str]:
    if not quotes:
        raise ValueError("No option quotes are available")
    providers = {quote.provider.lower() for chain in quotes.values() for quote in chain}
    feeds = {(quote.feed or "unknown").lower() for chain in quotes.values() for quote in chain}
    qualities = {quote.price_type for chain in quotes.values() for quote in chain}
    batches = {quote.batch_id for chain in quotes.values() for quote in chain}
    if len(providers) != 1 or len(feeds) != 1 or len(qualities) != 1:
        raise ValueError("Mixed provider, feed, or price type is not a valid calculation input")
    if any(batch is not None for batch in batches) and len(batches) != 1:
        raise ValueError("Mixed collection batches are not a valid calculation input")
    timestamps = [quote.timestamp for chain in quotes.values() for quote in chain]
    if max(timestamps) - min(timestamps) > timedelta(minutes=5):
        raise ValueError("Option quotes are not from a coherent valuation window")
    return f"{next(iter(providers))}:{next(iter(feeds))}", next(iter(qualities))


class HistoricalSVIXCalculator:
    def __init__(self, database: Session, engine: SVIXEngine | None = None):
        self.database = database
        self.engine = engine or SVIXEngine()
        self.options = OptionRepository(database)
        self.stocks = QuoteRepository(database)
        self.history = SVIXRepository(database)

    def _provider(self) -> str:
        configured = self.database.query(ProviderCredential).filter_by(enabled=True).first()
        provider = configured.provider if configured else get_settings().data_provider
        return provider

    def _available_dates(self, provider: str, start: date, end: date, frequency: Frequency) -> list[date]:
        rows = self.database.query(OptionSnapshot.timestamp).filter(OptionSnapshot.provider == provider, OptionSnapshot.timestamp >= _bounds(start), OptionSnapshot.timestamp <= _bounds(end, end=True)).order_by(OptionSnapshot.timestamp.asc()).all()
        dates = sorted({timestamp.date() for (timestamp,) in rows})
        if frequency == "daily":
            return dates
        by_week: dict[tuple[int, int], date] = {}
        for item in dates:
            iso = item.isocalendar()
            by_week[(iso.year, iso.week)] = item
        return list(by_week.values())

    def _symbols(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys((*DEFAULT_UNIVERSE, *custom_symbols(self.database))))

    def _day_quotes(self, provider: str, calculation_date: date, symbols: tuple[str, ...], *, strict: bool) -> dict[str, list[OptionQuote]]:
        grouped: dict[str, list[OptionQuote]] = {}
        latest_batch = None
        if strict:
            latest_row = self.database.query(OptionSnapshot).filter(
                OptionSnapshot.provider == provider,
                OptionSnapshot.timestamp >= _bounds(calculation_date),
                OptionSnapshot.timestamp <= _bounds(calculation_date, end=True),
                OptionSnapshot.batch_id.is_not(None),
                OptionSnapshot.price_type == "bbo",
                OptionSnapshot.delayed.is_not(True),
            ).order_by(OptionSnapshot.timestamp.desc()).first()
            latest_batch = latest_row.batch_id if latest_row else None
        for symbol in symbols:
            snapshots = self.options.by_time_range(symbol, provider, _bounds(calculation_date), _bounds(calculation_date, end=True))
            if strict:
                eligible = [
                    row for row in snapshots
                    if row.batch_id == latest_batch and row.price_type == "bbo" and not row.delayed
                ]
                snapshots = eligible
            latest_per_contract: dict[str, OptionSnapshot] = {}
            for snapshot in snapshots:
                if snapshot.contract_id not in latest_per_contract or snapshot.timestamp > latest_per_contract[snapshot.contract_id].timestamp:
                    latest_per_contract[snapshot.contract_id] = snapshot
            if latest_per_contract:
                grouped[symbol] = [_snapshot_to_quote(snapshot) for snapshot in latest_per_contract.values()]
        return grouped

    def _historical_market_data(self, provider: str, as_of: date, symbols: tuple[str, ...]) -> tuple[dict[str, dict[date, float]], dict[str, float]]:
        start = _bounds(as_of - timedelta(days=400))
        end = _bounds(as_of, end=True)
        histories: dict[str, dict[date, float]] = {}
        spots: dict[str, float] = {}
        for symbol in symbols:
            latest_by_day = {}
            for snapshot in self.stocks.by_time_range(symbol, provider, start, end):
                if snapshot.price is not None:
                    latest_by_day[snapshot.timestamp.date()] = snapshot
            if latest_by_day:
                histories[symbol] = {item: latest_by_day[item].price for item in sorted(latest_by_day)}
                spots[symbol] = latest_by_day[max(latest_by_day)].price
        return histories, spots

    def calculate_svix(self, start_date: date, end_date: date, frequency: Frequency = "daily", *, strict: bool = False) -> list[SVIXResult]:
        if end_date < start_date:
            raise ValueError("end_date must not be before start_date")
        provider = self._provider()
        results: list[SVIXResult] = []
        symbols = self._symbols()
        custom_definitions = enabled_definitions(self.database)
        for calculation_date in self._available_dates(provider, start_date, end_date, frequency):
            all_quotes = self._day_quotes(provider, calculation_date, symbols, strict=strict)
            histories, all_spots = self._historical_market_data(provider, calculation_date, symbols)
            standard_symbols = set(DEFAULT_UNIVERSE) & set(all_quotes) & set(histories)
            returns = _aligned_returns(histories, standard_symbols)
            available = standard_symbols & set(returns)
            quotes = {symbol: all_quotes[symbol] for symbol in available}
            spots = {symbol: all_spots[symbol] for symbol in available}
            if not quotes or not returns:
                logger.warning("Skipping %s: incomplete option snapshot universe", calculation_date.isoformat())
            else:
                valuation_time = max(quote.timestamp for chain in quotes.values() for quote in chain)
                source_feed, market_data_quality = _quote_identity(quotes)
                approximate = False if strict else market_data_quality != "bbo" or any(quote.delayed for chain in quotes.values() for quote in chain)
                try:
                    result = self.engine.calculate(quotes, returns, valuation_time, underlying_prices=spots, approximate=approximate, source_feed=source_feed, market_data_quality=market_data_quality)
                    self.history.save(result)
                    results.append(result)
                except (SVIXError, ValueError) as exc:
                    logger.warning("Skipping standard SVIX on %s: %s", calculation_date.isoformat(), exc)
            for definition in custom_definitions:
                try:
                    requested = set(definition.weights) & set(all_quotes) & set(histories)
                    custom_returns = _aligned_returns(histories, requested)
                    custom_available = requested & set(custom_returns)
                    custom_quotes = {symbol: all_quotes[symbol] for symbol in custom_available}
                    custom_spots = {symbol: all_spots[symbol] for symbol in custom_available}
                    custom_source, custom_quality = _quote_identity(custom_quotes)
                    custom_approximate = False if strict else custom_quality != "bbo" or any(quote.delayed for chain in custom_quotes.values() for quote in chain)
                    custom_result = calculate_custom_index(definition, custom_quotes, custom_returns, max(quote.timestamp for chain in custom_quotes.values() for quote in chain), engine=self.engine, underlying_prices=custom_spots, approximate=custom_approximate, source_feed=custom_source)
                    save_custom_result(self.database, definition, custom_result)
                except (SVIXError, ValueError) as exc:
                    logger.warning("Skipping custom index %s on %s: %s", definition.index.id, calculation_date.isoformat(), exc)
        self.database.commit()
        return results


def calculate_svix(database: Session, start_date: date, end_date: date, frequency: Frequency = "daily", *, strict: bool = False) -> list[SVIXResult]:
    """Service-compatible entry point for later queue/scheduler integration."""
    return HistoricalSVIXCalculator(database).calculate_svix(start_date, end_date, frequency, strict=strict)
