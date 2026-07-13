"""Provider-independent orchestration of the complete 30-day SVIX result."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, Mapping

from app.data.models import OptionQuote
from app.svix.constants import DEFAULT_RISK_FREE_RATE, TARGET_DAYS
from app.svix.correlation import calculate_correlation_matrix
from app.svix.exceptions import SVIXError
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

    def calculate_asset_term(self, symbol: str, quotes: Iterable[OptionQuote], valuation_time: datetime, underlying_price: float | None = None, approximate: bool = False) -> TermStructureResult:
        by_expiry: dict[datetime, list[OptionQuote]] = defaultdict(list)
        for quote in quotes:
            if quote.symbol == symbol:
                by_expiry[quote.expiry].append(quote)
        if not approximate:
            variances = [calculate_expiry_variance(symbol, expiry, chain, valuation_time, self.risk_free_rate, self.allow_last_price_fallback) for expiry, chain in by_expiry.items()]
            return interpolate_term_structure(symbol, variances, self.target_days)
        variances = []
        for expiry, chain in by_expiry.items():
            try:
                variances.append(calculate_expiry_variance(symbol, expiry, chain, valuation_time, self.risk_free_rate, True, fallback_forward_price=underlying_price))
            except SVIXError:
                continue
        return interpolate_term_structure(symbol, variances, self.target_days, allow_nearest_fallback=True)

    @staticmethod
    def _normalize(weights: Mapping[str, float]) -> dict[str, float]:
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("At least one positive component weight is required")
        return {symbol: value / total for symbol, value in weights.items()}

    @staticmethod
    def _component_volatility(symbols: tuple[str, ...], weights: Mapping[str, float], volatilities: Mapping[str, float], historical_returns: Mapping[str, Iterable[float]]) -> float:
        available = tuple(symbol for symbol in symbols if symbol in weights)
        if not available:
            raise ValueError(f"No available assets for component: {symbols}")
        component_weights = SVIXEngine._normalize({symbol: weights[symbol] for symbol in available})
        if len(available) == 1:
            return volatilities[available[0]]
        correlation = calculate_correlation_matrix({symbol: historical_returns[symbol] for symbol in available})
        return calculate_portfolio_variance(component_weights, {symbol: volatilities[symbol] for symbol in available}, correlation).volatility

    def calculate(self, option_quotes: Mapping[str, Iterable[OptionQuote]], historical_returns: Mapping[str, Iterable[float]], valuation_time: datetime, soxx_constituent_exposure: Mapping[str, float] | None = None, underlying_prices: Mapping[str, float] | None = None, approximate: bool = False, source_feed: str | None = None) -> SVIXResult:
        input_available = set(option_quotes) & set(historical_returns)
        terms: dict[str, TermStructureResult] = {}
        for symbol in input_available:
            try:
                terms[symbol] = self.calculate_asset_term(symbol, option_quotes[symbol], valuation_time, (underlying_prices or {}).get(symbol), approximate)
            except (SVIXError, ValueError):
                if not approximate:
                    raise
        available = set(terms)
        if "SOXX" not in available or not available.intersection({"MU", "SKHY"}) or not available.intersection({"NVDA", "AMD", "AVGO"}):
            raise ValueError("Core, Memory and AI components each require at least one available asset")
        original_weights = combined_asset_weights()
        coverage = sum(weight for symbol, weight in original_weights.items() if symbol in available) / sum(original_weights.values())
        base_weights = self._normalize({symbol: weight for symbol, weight in original_weights.items() if symbol in available})
        overlap = deoverlap_weights(base_weights, soxx_constituent_exposure)
        volatilities = {symbol: term.volatility for symbol, term in terms.items()}
        correlation = calculate_correlation_matrix({symbol: historical_returns[symbol] for symbol in overlap.adjusted_weights})
        portfolio = calculate_portfolio_variance(overlap.adjusted_weights, volatilities, correlation)
        memory = self._component_volatility(("MU", "SKHY"), overlap.adjusted_weights, volatilities, historical_returns)
        ai = self._component_volatility(("NVDA", "AMD", "AVGO"), overlap.adjusted_weights, volatilities, historical_returns)
        delayed_or_proxy = any(quote.delayed for chain in option_quotes.values() for quote in chain)
        source_quality = 0.65 if delayed_or_proxy else 1.0
        quality = min(term.calculation_quality for term in terms.values()) * coverage * source_quality
        return SVIXResult(timestamp=valuation_time, svix=portfolio.volatility * 100.0, core_vol=volatilities["SOXX"] * 100.0, memory_vol=memory * 100.0, ai_vol=ai * 100.0, weights=overlap.adjusted_weights, correlation_matrix=correlation.matrix, calculation_quality=quality, estimated=approximate, source_feed=source_feed)
