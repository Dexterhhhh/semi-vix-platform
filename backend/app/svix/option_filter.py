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
    bids: dict[float, dict[str, float | None]] = defaultdict(dict)
    for quote in quotes:
        mid = option_mid(quote, allow_last_price_fallback)
        if mid is not None:
            if quote.option_type in pairs[quote.strike]:
                raise InsufficientOptionData(
                    f"Duplicate {quote.option_type} quote at strike {quote.strike:g}"
                )
            pairs[quote.strike][quote.option_type] = mid
            bids[quote.strike][quote.option_type] = quote.bid
    k0_pair = pairs.get(k0.strike, {})
    if not allow_unpaired_k0 and ("C" not in k0_pair or "P" not in k0_pair):
        raise InsufficientOptionData("K0 requires both a valid call and put midpoint")
    selected: dict[float, tuple[str, float]] = {}

    def add_wing(strikes: list[float], option_type: str) -> None:
        consecutive_zero_bids = 0
        for strike in strikes:
            values = pairs[strike]
            if option_type not in values:
                continue
            bid = bids[strike].get(option_type)
            if bid is not None and bid <= 0:
                consecutive_zero_bids += 1
                if consecutive_zero_bids >= 2:
                    break
                continue
            consecutive_zero_bids = 0
            selected[strike] = (option_type, values[option_type])

    add_wing(sorted((strike for strike in pairs if strike < k0.strike), reverse=True), "P")
    add_wing(sorted(strike for strike in pairs if strike > k0.strike), "C")
    if "C" in k0_pair and "P" in k0_pair:
        selected[k0.strike] = ("K0", (k0_pair["C"] + k0_pair["P"]) / 2.0)
    elif allow_unpaired_k0:
        if "C" in k0_pair:
            selected[k0.strike] = ("K0-C", k0_pair["C"])
        elif "P" in k0_pair:
            selected[k0.strike] = ("K0-P", k0_pair["P"])
    intervals = strike_intervals(list(selected))
    options = [FilteredOption(strike=strike, delta_k=intervals[strike], option_price=selected[strike][1], option_type=selected[strike][0]) for strike in sorted(selected)]
    if len(options) < 2:
        raise InsufficientOptionData("Insufficient OTM option prices after filtering")
    return FilteredOptionSet(symbol=symbol, expiry=expiry, k0=k0, options=options, forward=forward)
