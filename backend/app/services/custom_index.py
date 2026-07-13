"""Versioned custom-index configuration, calculation and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.models import OptionQuote
from app.database.models import CustomIndex, CustomIndexComponent, CustomIndexHistory, CustomIndexVersion
from app.svix.correlation import calculate_correlation_matrix
from app.svix.engine import SVIXEngine
from app.svix.exceptions import SVIXError
from app.svix.portfolio import calculate_portfolio_variance


@dataclass(frozen=True)
class CustomIndexDefinition:
    index: CustomIndex
    version: CustomIndexVersion
    weights: dict[str, float]


@dataclass(frozen=True)
class CustomIndexResult:
    timestamp: datetime
    value: float
    calculation_quality: float
    estimated: bool
    source_feed: str | None


def latest_definition(database: Session, index: CustomIndex) -> CustomIndexDefinition | None:
    version = database.query(CustomIndexVersion).filter_by(custom_index_id=index.id).order_by(CustomIndexVersion.version_number.desc()).first()
    if version is None:
        return None
    components = database.query(CustomIndexComponent).filter_by(version_id=version.id).order_by(CustomIndexComponent.symbol).all()
    return CustomIndexDefinition(index=index, version=version, weights={item.symbol: item.weight for item in components})


def enabled_definitions(database: Session) -> list[CustomIndexDefinition]:
    return [definition for index in database.query(CustomIndex).filter_by(enabled=True).order_by(CustomIndex.id).all() if (definition := latest_definition(database, index)) is not None]


def custom_symbols(database: Session) -> tuple[str, ...]:
    return tuple(sorted({symbol for definition in enabled_definitions(database) for symbol in definition.weights}))


def next_version_number(database: Session, custom_index_id: int) -> int:
    return int(database.query(func.max(CustomIndexVersion.version_number)).filter_by(custom_index_id=custom_index_id).scalar() or 0) + 1


def calculate_custom_index(definition: CustomIndexDefinition, option_quotes: Mapping[str, Iterable[OptionQuote]], historical_returns: Mapping[str, Iterable[float]], valuation_time: datetime, *, engine: SVIXEngine | None = None, underlying_prices: Mapping[str, float] | None = None, approximate: bool = False, source_feed: str | None = None) -> CustomIndexResult:
    calculator = engine or SVIXEngine()
    requested = set(definition.weights)
    input_available = requested & set(option_quotes) & set(historical_returns)
    terms = {}
    for symbol in input_available:
        try:
            terms[symbol] = calculator.calculate_asset_term(symbol, option_quotes[symbol], valuation_time, (underlying_prices or {}).get(symbol), approximate)
        except (SVIXError, ValueError):
            if not approximate and definition.version.missing_policy == "STRICT":
                raise
    available = set(terms)
    if definition.version.missing_policy == "STRICT" and available != requested:
        missing = ", ".join(sorted(requested - available))
        raise ValueError(f"Custom index is missing required symbols: {missing}")
    coverage = sum(definition.weights[symbol] for symbol in available)
    if not available or (definition.version.missing_policy == "RENORMALIZE" and coverage < 0.5):
        raise ValueError("Custom index has less than 50% usable weight")
    weights = {symbol: definition.weights[symbol] / coverage for symbol in available}
    volatilities = {symbol: terms[symbol].volatility for symbol in available}
    if len(available) == 1:
        volatility = volatilities[next(iter(available))]
    else:
        correlation = calculate_correlation_matrix({symbol: historical_returns[symbol] for symbol in available})
        volatility = calculate_portfolio_variance(weights, volatilities, correlation).volatility
    delayed = any(quote.delayed for symbol in available for quote in option_quotes[symbol])
    source_quality = 0.65 if delayed else 1.0
    quality = min(terms[symbol].calculation_quality for symbol in available) * coverage * source_quality
    return CustomIndexResult(timestamp=valuation_time, value=volatility * 100.0, calculation_quality=quality, estimated=approximate, source_feed=source_feed)


def save_custom_result(database: Session, definition: CustomIndexDefinition, result: CustomIndexResult) -> CustomIndexHistory:
    record = database.query(CustomIndexHistory).filter_by(custom_index_id=definition.index.id, version_id=definition.version.id, timestamp=result.timestamp).first()
    if record is None:
        record = CustomIndexHistory(custom_index_id=definition.index.id, version_id=definition.version.id, timestamp=result.timestamp, value=result.value, calculation_quality=result.calculation_quality, estimated=result.estimated, source_feed=result.source_feed)
        database.add(record)
        return record
    if not record.estimated and result.estimated:
        return record
    record.value = result.value
    record.calculation_quality = result.calculation_quality
    record.estimated = result.estimated
    record.source_feed = result.source_feed
    return record
