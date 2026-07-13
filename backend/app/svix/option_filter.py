"""VIX-style OTM option selection and strike spacing."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.data.models import OptionQuote
from app.svix.exceptions import InsufficientOptionData
from app.svix.forward import option_mid
from app.svix.models import FilteredOption, FilteredOptionSet, ForwardResult, K0Result


def strike_intervals(strikes: list[float]) -> dict[float, float]:
    if len(strikes) < 2:
        raise InsufficientOptionData("At least two strikes are required for variance replication")
    ordered = sorted(set(strikes))
    if len(ordered) < 2:
        raise InsufficientOptionData("At least two distinct strikes are required")
    intervals = {ordered[0]: ordered[1] - ordered[0], ordered[-1]: ordered[-1] - ordered[-2]}
    for index in range(1, len(ordered) - 1):
        intervals[ordered[index]] = (ordered[index + 1] - ordered[index - 1]) / 2.0
    if any(interval <= 0 for interval in intervals.values()):
        raise InsufficientOptionData("Strikes must be strictly increasing")
    return intervals


def filter_otm_options(symbol: str, expiry, quotes: Iterable[OptionQuote], k0: K0Result, forward: ForwardResult, allow_last_price_fallback: bool = False, allow_unpaired_k0: bool = False) -> FilteredOptionSet:
    """Choose puts below K0, calls above K0, and the call/put average at K0."""
    pairs: dict[float, dict[str, float]] = defaultdict(dict)
    for quote in quotes:
        mid = option_mid(quote, allow_last_price_fallback)
        if mid is not None:
            pairs[quote.strike][quote.option_type] = mid
    k0_pair = pairs.get(k0.strike, {})
    if not allow_unpaired_k0 and ("C" not in k0_pair or "P" not in k0_pair):
        raise InsufficientOptionData("K0 requires both a valid call and put midpoint")
    selected: dict[float, tuple[str, float]] = {}
    for strike, values in pairs.items():
        if strike < k0.strike and "P" in values:
            selected[strike] = ("P", values["P"])
        elif strike > k0.strike and "C" in values:
            selected[strike] = ("C", values["C"])
        elif strike == k0.strike and "C" in values and "P" in values:
            selected[strike] = ("K0", (values["C"] + values["P"]) / 2.0)
        elif strike == k0.strike and allow_unpaired_k0:
            if "C" in values:
                selected[strike] = ("K0-C", values["C"])
            elif "P" in values:
                selected[strike] = ("K0-P", values["P"])
    intervals = strike_intervals(list(selected))
    options = [FilteredOption(strike=strike, delta_k=intervals[strike], option_price=selected[strike][1], option_type=selected[strike][0]) for strike in sorted(selected)]
    if len(options) < 2:
        raise InsufficientOptionData("Insufficient OTM option prices after filtering")
    return FilteredOptionSet(symbol=symbol, expiry=expiry, k0=k0, options=options, forward=forward)
