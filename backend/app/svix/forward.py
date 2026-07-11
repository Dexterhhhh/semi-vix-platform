"""Put-call parity forward and K0 selection."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from app.data.models import OptionQuote
from app.svix.exceptions import InsufficientOptionData, InvalidForwardPrice
from app.svix.models import ForwardResult, K0Result


def option_mid(quote: OptionQuote, allow_last_price_fallback: bool = False) -> float | None:
    """Return a positive midpoint, optionally falling back to a valid last price."""
    if quote.bid is not None and quote.ask is not None:
        midpoint = (quote.bid + quote.ask) / 2.0
        if math.isfinite(midpoint) and midpoint > 0:
            return midpoint
    if allow_last_price_fallback and quote.last is not None and math.isfinite(quote.last) and quote.last > 0:
        return quote.last
    return None


def calculate_forward(quotes: Iterable[OptionQuote], time_to_expiry: float, risk_free_rate: float = 0.0, allow_last_price_fallback: bool = False) -> ForwardResult:
    """Use the valid strike pair with the smallest absolute call-put difference."""
    if time_to_expiry <= 0:
        raise InvalidForwardPrice("Time to expiry must be positive")
    pairs: dict[float, dict[str, float]] = defaultdict(dict)
    for quote in quotes:
        mid = option_mid(quote, allow_last_price_fallback)
        if mid is not None:
            pairs[quote.strike][quote.option_type] = mid
    eligible = [(strike, values["C"], values["P"]) for strike, values in pairs.items() if "C" in values and "P" in values]
    if not eligible:
        raise InsufficientOptionData("At least one valid call-put pair is required for put-call parity")
    reference_strike, call, put = min(eligible, key=lambda item: (abs(item[1] - item[2]), item[0]))
    forward = reference_strike + math.exp(risk_free_rate * time_to_expiry) * (call - put)
    if not math.isfinite(forward) or forward <= 0:
        raise InvalidForwardPrice("Put-call parity produced an invalid forward price")
    quality = min(1.0, len(eligible) / 3.0)
    return ForwardResult(forward_price=forward, reference_strike=reference_strike, quality_score=quality, pair_count=len(eligible))


def select_k0(strikes: Iterable[float], forward_price: float) -> K0Result:
    """Select the largest strike no greater than F, with an explicit nearest fallback."""
    valid = sorted({float(strike) for strike in strikes if math.isfinite(float(strike)) and float(strike) > 0})
    if not valid:
        raise InsufficientOptionData("No valid strikes are available for K0 selection")
    below = [strike for strike in valid if strike <= forward_price]
    if below:
        return K0Result(strike=below[-1], used_nearest_fallback=False)
    return K0Result(strike=min(valid, key=lambda strike: abs(strike - forward_price)), used_nearest_fallback=True)
