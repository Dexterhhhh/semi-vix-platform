"""Provider-independent orchestration of the complete 30-day SVIX result."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, Mapping

from app.data.models import OptionQuote
from app.svix.constants import DEFAULT_RISK_FREE_RATE, TARGET_DAYS
from app.svix.correlation import calculate_correlation_matrix
from app.svix.interpolation import interpolate_term_structure
from app.svix.models import SVIXResult, TermStructureResult
from app.svix.portfolio import calculate_portfolio_variance
from app.svix.variance import calculate_expiry_variance
from app.svix.weighting import combined_asset_weights, deoverlap_weights


class SVIXEngine:
    """Pure calculation engine; it consumes only normalized option quotes."""

    def __init__(self, risk_free_rate: float = DEFAULT_RISK_FREE_RATE, target_days: int = TARGET_DAYS, allow_last_price_fallback: bool = False):
        self.risk_free_rate = risk_free_rate
        self.target_days = target_days
        self.allow_last_price_fallback = allow_last_price_fallback

    def calculate_asset_term(self, symbol: str, quotes: Iterable[OptionQuote], valuation_time: datetime) -> TermStructureResult:
        by_expiry: dict[datetime, list[OptionQuote]] = defaultdict(list)
        for quote in quotes:
            if quote.symbol == symbol:
                by_expiry[quote.expiry].append(quote)
        variances = [calculate_expiry_variance(symbol, expiry, chain, valuation_time, self.risk_free_rate, self.allow_last_price_fallback) for expiry, chain in by_expiry.items()]
        return interpolate_term_structure(symbol, variances, self.target_days)

    def calculate(self, option_quotes: Mapping[str, Iterable[OptionQuote]], historical_returns: Mapping[str, Iterable[float]], valuation_time: datetime, soxx_constituent_exposure: Mapping[str, float] | None = None) -> SVIXResult:
        base_weights = combined_asset_weights()
        overlap = deoverlap_weights(base_weights, soxx_constituent_exposure)
        terms = {symbol: self.calculate_asset_term(symbol, option_quotes[symbol], valuation_time) for symbol in overlap.adjusted_weights}
        volatilities = {symbol: term.volatility for symbol, term in terms.items()}
        correlation = calculate_correlation_matrix({symbol: historical_returns[symbol] for symbol in overlap.adjusted_weights})
        portfolio = calculate_portfolio_variance(overlap.adjusted_weights, volatilities, correlation)
        memory_weights = {symbol: overlap.adjusted_weights[symbol] for symbol in ("MU", "SKHY")}
        memory_total = sum(memory_weights.values())
        memory_weights = {symbol: value / memory_total for symbol, value in memory_weights.items()}
        ai_weights = {symbol: overlap.adjusted_weights[symbol] for symbol in ("NVDA", "AMD", "AVGO")}
        ai_total = sum(ai_weights.values())
        ai_weights = {symbol: value / ai_total for symbol, value in ai_weights.items()}
        memory_correlation = calculate_correlation_matrix({symbol: historical_returns[symbol] for symbol in memory_weights})
        ai_correlation = calculate_correlation_matrix({symbol: historical_returns[symbol] for symbol in ai_weights})
        memory = calculate_portfolio_variance(memory_weights, {symbol: volatilities[symbol] for symbol in memory_weights}, memory_correlation)
        ai = calculate_portfolio_variance(ai_weights, {symbol: volatilities[symbol] for symbol in ai_weights}, ai_correlation)
        quality = min(term.calculation_quality for term in terms.values())
        return SVIXResult(timestamp=valuation_time, svix=portfolio.volatility * 100.0, core_vol=volatilities["SOXX"] * 100.0, memory_vol=memory.volatility * 100.0, ai_vol=ai.volatility * 100.0, weights=overlap.adjusted_weights, correlation_matrix=correlation.matrix, calculation_quality=quality)
