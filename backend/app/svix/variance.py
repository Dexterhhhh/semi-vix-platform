"""Single-expiry VIX-style implied variance replication."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable

from app.data.models import OptionQuote
from app.svix.constants import CALENDAR_DAYS_PER_YEAR
from app.svix.exceptions import InvalidVariance, SVIXError
from app.svix.forward import calculate_forward, option_mid, select_k0
from app.svix.models import ForwardResult, VarianceResult
from app.svix.option_filter import filter_otm_options


def time_to_expiry_years(valuation_time: datetime, expiry: datetime) -> float:
    if valuation_time.tzinfo is None or expiry.tzinfo is None:
        raise InvalidVariance("Valuation time and expiry must be timezone-aware")
    seconds = (expiry.astimezone(timezone.utc) - valuation_time.astimezone(timezone.utc)).total_seconds()
    return seconds / (CALENDAR_DAYS_PER_YEAR * 24.0 * 60.0 * 60.0)


def calculate_expiry_variance(symbol: str, expiry: datetime, quotes: Iterable[OptionQuote], valuation_time: datetime, risk_free_rate: float = 0.0, allow_last_price_fallback: bool = False, fallback_forward_price: float | None = None) -> VarianceResult:
    """Calculate annual implied variance for one expiry without fabricating quotes."""
    chain = list(quotes)
    time_to_expiry = time_to_expiry_years(valuation_time, expiry)
    if time_to_expiry <= 0:
        raise InvalidVariance("Expiry must be after valuation time")
    used_spot_forward = False
    try:
        forward = calculate_forward(chain, time_to_expiry, risk_free_rate, allow_last_price_fallback)
    except SVIXError:
        if fallback_forward_price is None or not math.isfinite(fallback_forward_price) or fallback_forward_price <= 0:
            raise
        used_spot_forward = True
        forward = ForwardResult(forward_price=fallback_forward_price, reference_strike=fallback_forward_price, quality_score=0.25, pair_count=0)
    rights_by_strike: dict[float, set[str]] = {}
    for quote in chain:
        if option_mid(quote, allow_last_price_fallback) is not None:
            rights_by_strike.setdefault(quote.strike, set()).add(quote.option_type)
    k0_strikes = (strike for strike, rights in rights_by_strike.items() if used_spot_forward or {"C", "P"}.issubset(rights))
    k0 = select_k0(k0_strikes, forward.forward_price)
    filtered = filter_otm_options(symbol, expiry, chain, k0, forward, allow_last_price_fallback, allow_unpaired_k0=used_spot_forward)
    discounted_sum = sum(option.delta_k / (option.strike ** 2) * math.exp(risk_free_rate * time_to_expiry) * option.option_price for option in filtered.options)
    variance = (2.0 / time_to_expiry) * discounted_sum - (1.0 / time_to_expiry) * ((forward.forward_price / k0.strike) - 1.0) ** 2
    used_uncorrected_variance = False
    if not math.isfinite(variance) or variance <= 0:
        if fallback_forward_price is None:
            raise InvalidVariance("Variance replication produced a non-positive variance")
        variance = (2.0 / time_to_expiry) * discounted_sum
        used_uncorrected_variance = True
    if not math.isfinite(variance) or variance <= 0:
        raise InvalidVariance("Variance replication produced a non-positive variance")
    return VarianceResult(symbol=symbol, expiry=expiry, variance=variance, days_to_expiry=time_to_expiry * CALENDAR_DAYS_PER_YEAR, forward_price=forward.forward_price, option_count=len(filtered.options), quality_metrics={"forward_quality": forward.quality_score, "k0_fallback": float(k0.used_nearest_fallback), "parity_pairs": float(forward.pair_count), "spot_forward": float(used_spot_forward), "uncorrected_variance": float(used_uncorrected_variance)})
