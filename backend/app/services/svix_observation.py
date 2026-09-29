"""Batch-scoped, auditable free-feed intraday observations.

A collection batch is the only source of new option quotes. Reuse is limited to
persisted single-asset calculations from the same market session and method.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import json
import math
from typing import Any

from sqlalchemy.orm import Session

from app.database.models import (
    MarketCollectionRun, OptionSnapshot, StockSnapshot, SVIXAssetObservation,
    SVIXCorrelationCache, SVIXObservation,
)
from app.scheduler.market_hours import _calendar
from app.services.svix_calculator import _snapshot_to_quote
from app.svix.correlation import calculate_correlation_matrix, calculate_returns
from app.svix.exceptions import SVIXError
from app.svix.interpolation import interpolate_term_structure
from app.svix.portfolio import calculate_portfolio_variance
from app.svix.variance import calculate_expiry_variance
from app.svix.weighting import combined_asset_weights


@dataclass(frozen=True)
class ObservationRules:
    method_version: str = "semivix-observe-v1"
    fresh_minutes: int = 5
    max_quote_minutes: int = 15
    max_cache_minutes: int = 10
    min_coverage: float = 0.70
    max_single_expiry_distance_days: float = 7.0
    max_correlation_trading_days: int = 5


RULES = ObservationRules()
WEIGHTS = combined_asset_weights()
GROUPS = {"core": ("SOXX",), "memory": ("MU", "SKHY"), "ai": ("NVDA", "AMD", "AVGO")}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _age_minutes(now: datetime, timestamp: datetime | None) -> float | None:
    if timestamp is None:
        return None
    return (now - timestamp).total_seconds() / 60


def _previous_session(session_date: date) -> date | None:
    schedule = _calendar().schedule(start_date=session_date - timedelta(days=14), end_date=session_date - timedelta(days=1))
    return schedule.index[-1].date() if not schedule.empty else None


def _sessions_ago(session_date: date, older: date) -> int:
    schedule = _calendar().schedule(start_date=older, end_date=session_date)
    return max(0, len(schedule) - 1)


def _latest_asset(database: Session, symbol: str, session_date: date, before: datetime, method: str) -> SVIXAssetObservation | None:
    return database.query(SVIXAssetObservation).filter(
        SVIXAssetObservation.symbol == symbol,
        SVIXAssetObservation.session_date == session_date,
        SVIXAssetObservation.method_version == method,
        SVIXAssetObservation.status == "NEW",
        SVIXAssetObservation.valuation_at < before,
    ).order_by(SVIXAssetObservation.valuation_at.desc()).first()


def _stock_spot(database: Session, batch_id: str, symbol: str, provider: str, valuation_at: datetime, rules: ObservationRules) -> tuple[float | None, datetime | None]:
    rows = database.query(StockSnapshot).filter_by(batch_id=batch_id, symbol=symbol, provider=provider).order_by(StockSnapshot.id.desc()).all()
    for row in rows:
        age = _age_minutes(valuation_at, row.trade_timestamp)
        if row.price is not None and math.isfinite(row.price) and row.price > 0 and age is not None and 0 <= age <= rules.max_quote_minutes:
            return row.price, row.trade_timestamp
    return None, None


def _calculate_asset(database: Session, symbol: str, rows: list[OptionSnapshot], provider: str, batch_id: str, valuation_at: datetime, rules: ObservationRules) -> dict[str, Any]:
    rejected: dict[str, int] = defaultdict(int)
    by_expiry: dict[datetime, list] = defaultdict(list)
    feeds: set[str] = set()
    for row in rows:
        age = _age_minutes(valuation_at, row.timestamp)
        expiry = datetime.combine(row.expiry.date(), time(21, 0), tzinfo=timezone.utc) if row.provider == "ALPACA" else row.expiry
        if row.price_type not in {"bbo", "indicative_quote"}:
            rejected["UNSUPPORTED_PRICE_TYPE"] += 1
        elif age is None or age < 0 or age > rules.max_quote_minutes:
            rejected["QUOTE_TIME_OUT_OF_RANGE"] += 1
        elif expiry <= valuation_at:
            rejected["EXPIRED_CONTRACT"] += 1
        elif row.bid is None or row.ask is None or not all(math.isfinite(value) and value >= 0 for value in (row.bid, row.ask)) or row.bid > row.ask:
            rejected["INVALID_SPREAD"] += 1
        else:
            quote = _snapshot_to_quote(row)
            by_expiry[quote.expiry].append(quote)
            feeds.add(f"{row.provider.lower()}:{(row.feed or 'unknown').lower()}")
    if len(feeds) > 1:
        return {"status": "MIXED_FEED", "rejected": dict(rejected)}
    spot, spot_at = _stock_spot(database, batch_id, symbol, provider, valuation_at, rules)
    variances = []
    errors = []
    for expiry, chain in by_expiry.items():
        try:
            variances.append(calculate_expiry_variance(symbol, expiry, chain, valuation_at, fallback_forward_price=spot))
        except (SVIXError, ValueError) as exc:
            errors.append(f"{expiry.date().isoformat()}: {type(exc).__name__}")
    near = any(item.days_to_expiry < 30 for item in variances)
    far = any(item.days_to_expiry > 30 for item in variances)
    exact = any(math.isclose(item.days_to_expiry, 30, abs_tol=1e-9) for item in variances)
    if len(variances) > 1 and not exact and not (near and far):
        return {"status": "MISSING_BRACKETING_EXPIRY", "rejected": dict(rejected), "expiry_errors": errors}
    try:
        term = interpolate_term_structure(symbol, variances, allow_nearest_fallback=True, max_fallback_distance_days=rules.max_single_expiry_distance_days)
    except (SVIXError, ValueError) as exc:
        return {"status": type(exc).__name__.upper(), "rejected": dict(rejected), "expiry_errors": errors}
    selected = [variance for variance in variances if variance.expiry in {term.near_expiry, term.next_expiry}]
    times = [timestamp for variance in selected for timestamp in variance.input_timestamps]
    used_contracts = sorted({contract for variance in selected for contract in variance.used_contract_ids})
    uses_spot = any(variance.quality_metrics.get("spot_forward") for variance in selected)
    if uses_spot and spot_at is not None:
        times.append(spot_at)
    if not times or not used_contracts:
        return {"status": "NO_USED_QUOTES", "rejected": dict(rejected)}
    oldest, newest = min(times), max(times)
    age = _age_minutes(valuation_at, oldest)
    if age is None or age < 0 or age > rules.max_quote_minutes:
        return {"status": "USED_QUOTE_EXPIRED", "rejected": dict(rejected)}
    return {
        "status": "NEW", "volatility": term.volatility * 100,
        "quality": term.calculation_quality, "oldest_input_at": oldest,
        "newest_input_at": newest, "term_method": "single_expiry" if term.next_expiry is None else "interpolated",
        "actual_days": selected[0].days_to_expiry if term.next_expiry is None else None,
        "used_contract_ids": used_contracts,
        "used_input_identity": [list(item) for item in sorted((row.contract_id, _iso(row.timestamp)) for row in rows if row.contract_id in used_contracts)],
        "used_spot_forward": bool(uses_spot), "spot_timestamp": _iso(spot_at) if uses_spot else None,
        "feed": next(iter(feeds)) if feeds else None,
        "quote_age_minutes": age,
        "quote_span_minutes": (newest - oldest).total_seconds() / 60,
        "rejected": dict(rejected), "expiry_errors": errors,
    }


def _prior_result(database: Session, symbol: str, run: MarketCollectionRun, rules: ObservationRules) -> tuple[SVIXAssetObservation | None, dict[str, Any] | None]:
    previous = _latest_asset(database, symbol, run.session_date, run.finished_at, rules.method_version)
    if previous is None or previous.oldest_input_at is None:
        return None, None
    previous_age = _age_minutes(run.finished_at, previous.valuation_at)
    quote_age = _age_minutes(run.finished_at, previous.oldest_input_at)
    if previous_age is None or quote_age is None or not 0 <= previous_age <= rules.max_cache_minutes or not 0 <= quote_age <= rules.max_quote_minutes:
        return None, None
    return previous, json.loads(previous.details)


def _correlation(database: Session, provider: str, session_date: date, valuation_at: datetime, assets: tuple[str, ...], rules: ObservationRules) -> tuple[list[list[float]] | None, date | None, str | None]:
    if len(assets) < 2:
        return [[1.0]], None, None
    previous_day = _previous_session(session_date)
    if previous_day is None:
        return None, None, "NO_PREVIOUS_SESSION"
    candidates = database.query(SVIXCorrelationCache).filter(
        SVIXCorrelationCache.provider == provider, SVIXCorrelationCache.as_of <= previous_day,
        SVIXCorrelationCache.available_at <= valuation_at,
    ).order_by(SVIXCorrelationCache.as_of.desc(), SVIXCorrelationCache.available_at.desc()).all()
    for cached in candidates:
        stored_assets = json.loads(cached.assets)
        if set(assets).issubset(stored_assets) and _sessions_ago(previous_day, cached.as_of) <= rules.max_correlation_trading_days:
            matrix = json.loads(cached.matrix)
            indices = [stored_assets.index(symbol) for symbol in assets]
            return [[matrix[i][j] for j in indices] for i in indices], cached.as_of, None
    # Only completed prior-session daily bars, available by valuation time, may
    # enter the matrix. Intraday snapshots are never treated as daily closes.
    histories: dict[str, dict[date, float]] = {}
    for symbol in assets:
        rows = database.query(StockSnapshot).filter(
            StockSnapshot.provider == provider, StockSnapshot.symbol == symbol,
            StockSnapshot.price_type.in_(("adjusted_close", "raw_close")),
            StockSnapshot.timestamp < datetime.combine(session_date, datetime.min.time(), tzinfo=timezone.utc),
            StockSnapshot.received_at <= valuation_at,
            StockSnapshot.timestamp >= datetime.combine(session_date - timedelta(days=450), datetime.min.time(), tzinfo=timezone.utc),
        ).order_by(StockSnapshot.timestamp.asc(), StockSnapshot.id.asc()).all()
        histories[symbol] = {row.timestamp.date(): row.price for row in rows if row.price is not None and row.price > 0}
    common = sorted(set.intersection(*(set(history) for history in histories.values())))
    if len(common) < 253:
        return None, None, "INSUFFICIENT_DAILY_HISTORY"
    aligned = {symbol: calculate_returns([histories[symbol][day] for day in common]) for symbol in assets}
    try:
        result = calculate_correlation_matrix(aligned)
    except SVIXError:
        return None, None, "INVALID_CORRELATION_HISTORY"
    as_of = common[-1]
    if _sessions_ago(previous_day, as_of) > rules.max_correlation_trading_days:
        return None, None, "CORRELATION_TOO_OLD"
    database.add(SVIXCorrelationCache(provider=provider, as_of=as_of, available_at=valuation_at, assets=json.dumps(result.assets), matrix=json.dumps(result.matrix)))
    database.flush()
    indices = [result.assets.index(symbol) for symbol in assets]
    return [[result.matrix[i][j] for j in indices] for i in indices], as_of, None


def _component(database: Session, provider: str, session_date: date, valuation_at: datetime, names: tuple[str, ...], assets: dict[str, dict[str, Any]], rules: ObservationRules) -> tuple[float | None, date | None, str | None]:
    present = tuple(sorted(set(names) & set(assets)))
    if not present:
        return None, None, "NO_ASSETS"
    if len(present) == 1:
        return assets[present[0]]["volatility"], None, None
    matrix, matrix_day, reason = _correlation(database, provider, session_date, valuation_at, present, rules)
    if matrix is None:
        return None, None, reason
    from app.svix.models import CorrelationMatrix
    corr = CorrelationMatrix(assets=list(present), matrix=matrix, observations=252)
    total = sum(WEIGHTS[name] for name in present)
    weights = {name: WEIGHTS[name] / total for name in present}
    volatility = {name: assets[name]["volatility"] / 100 for name in present}
    try:
        return calculate_portfolio_variance(weights, volatility, corr).volatility * 100, matrix_day, None
    except (SVIXError, ValueError):
        return None, matrix_day, "INVALID_PORTFOLIO_COVARIANCE"


def calculate_observation(database: Session, batch_id: str, rules: ObservationRules = RULES) -> SVIXObservation | None:
    run = database.query(MarketCollectionRun).filter_by(batch_id=batch_id).first()
    if run is None or run.finished_at is None or run.status == "RUNNING":
        raise ValueError("A completed collection run with this batch ID is required")
    existing = database.query(SVIXObservation).filter_by(batch_id=batch_id, method_version=rules.method_version).first()
    if existing:
        return existing
    if database.query(SVIXAssetObservation.id).filter_by(batch_id=batch_id, method_version=rules.method_version).first():
        return None
    rows = database.query(OptionSnapshot).filter_by(batch_id=batch_id).all()
    by_symbol: dict[str, list[OptionSnapshot]] = defaultdict(list)
    for row in rows:
        by_symbol[row.symbol].append(row)
    provider = rows[0].provider if rows else "ALPACA"
    assets: dict[str, dict[str, Any]] = {}
    diagnostics: dict[str, dict[str, Any]] = {}
    new_count = 0
    for symbol in WEIGHTS:
        current = _calculate_asset(database, symbol, by_symbol[symbol], provider, batch_id, run.finished_at, rules) if by_symbol[symbol] else {"status": "NO_BATCH_QUOTES"}
        latest_new = _latest_asset(database, symbol, run.session_date, run.finished_at, rules.method_version)
        prior_identity = json.loads(latest_new.details).get("used_input_identity") if latest_new else None
        previous, previous_data = _prior_result(database, symbol, run, rules)
        repeated = prior_identity is not None and current.get("status") == "NEW" and current["used_input_identity"] == prior_identity
        if repeated:
            current = {"status": "UNCHANGED_QUOTES"}
        if current["status"] == "NEW":
            new_count += 1
            current["source_batch_id"] = batch_id
            current["source_valuation_at"] = _iso(run.finished_at)
        elif previous is not None and previous_data is not None:
            current = {**previous_data, "status": "CACHED", "reason": current["status"], "source_batch_id": previous.batch_id, "source_valuation_at": _iso(previous.valuation_at)}
            current["quote_age_minutes"] = _age_minutes(run.finished_at, previous.oldest_input_at)
        diagnostics[symbol] = current
        if current["status"] in {"NEW", "CACHED"}:
            assets[symbol] = current
        database.add(SVIXAssetObservation(
            session_date=run.session_date, valuation_at=run.finished_at, batch_id=batch_id,
            method_version=rules.method_version, symbol=symbol,
            volatility=current.get("volatility"),
            oldest_input_at=datetime.fromisoformat(current["oldest_input_at"]) if isinstance(current.get("oldest_input_at"), str) else current.get("oldest_input_at"),
            newest_input_at=datetime.fromisoformat(current["newest_input_at"]) if isinstance(current.get("newest_input_at"), str) else current.get("newest_input_at"),
            term_method=current.get("term_method"), status=current["status"],
            details=json.dumps(current, default=str),
        ))
    if new_count == 0:
        run.calculation_status = "NO_NEW_DATA"
        database.commit()
        return None
    values: dict[str, float | None] = {}
    reasons: dict[str, str] = {}
    matrix_dates: dict[str, str] = {}
    for group, symbols in GROUPS.items():
        values[group], matrix_day, reason = _component(database, provider, run.session_date, run.finished_at, symbols, assets, rules)
        if matrix_day:
            matrix_dates[group] = matrix_day.isoformat()
        if reason:
            reasons[group] = reason
    coverage = sum(WEIGHTS[symbol] for symbol in assets)
    cached_coverage = sum(WEIGHTS[symbol] for symbol in assets if assets[symbol]["status"] == "CACHED")
    if "SOXX" not in assets:
        values["svix"] = None
        reasons["svix"] = "SOXX_UNAVAILABLE"
    elif coverage + 1e-12 < rules.min_coverage:
        values["svix"] = None
        reasons["svix"] = "INSUFFICIENT_COVERAGE"
    else:
        values["svix"], matrix_day, reason = _component(database, provider, run.session_date, run.finished_at, tuple(WEIGHTS), assets, rules)
        if matrix_day:
            matrix_dates["svix"] = matrix_day.isoformat()
        if reason:
            reasons["svix"] = reason
    has_old = any(value.get("quote_age_minutes", 0) > rules.fresh_minutes for value in assets.values())
    indicative = any((value.get("feed") or "").endswith(":indicative") for value in assets.values())
    status = "CACHED" if cached_coverage else "OLD_QUOTES" if has_old else "PARTIAL_COVERAGE" if coverage < 1 else "FREE_ESTIMATE" if indicative else "ESTIMATE"
    if all(value is None for value in values.values()):
        status = "NO_VALID_DATA"
    details = {
        "assets": diagnostics, "component_counts": {name: f"{len(set(symbols) & set(assets))}/{len(symbols)}" for name, symbols in GROUPS.items()},
        "component_status": {name: "AVAILABLE" if value is not None else reasons.get(name, "NO_VALID_DATA") for name, value in values.items()},
        "actual_weights": {symbol: WEIGHTS[symbol] / coverage for symbol in assets} if coverage else {},
        "reasons": reasons, "matrix_dates": matrix_dates,
        "oldest_input_at": _iso(min((value["oldest_input_at"] if isinstance(value["oldest_input_at"], datetime) else datetime.fromisoformat(value["oldest_input_at"]) for value in assets.values()), default=None)),
        "new_count": new_count,
        "rules": rules.__dict__,
    }
    observation = SVIXObservation(
        session_date=run.session_date, valuation_at=run.finished_at, batch_id=batch_id,
        method_version=rules.method_version, svix=values["svix"], core=values["core"],
        memory=values["memory"], ai=values["ai"], status=status,
        coverage=coverage, cached_coverage=cached_coverage,
        source_feed=next((item.get("feed") for item in assets.values() if item.get("feed")), None),
        details=json.dumps(details, default=str),
    )
    database.add(observation)
    run.calculation_status = "PARTIAL" if any(value is None for value in values.values()) else "COMPLETED"
    database.commit()
    return observation
