"""Symbol syntax and the canonical default-index universe."""

import re

DEFAULT_SYMBOLS = ("SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO")
SUPPORTED_SYMBOLS = frozenset(DEFAULT_SYMBOLS)


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    # Provider adapters may collect custom-index constituents.  Membership in
    # DEFAULT_SYMBOLS is a portfolio concern, not a ticker-format concern.
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", normalized):
        from app.data.exceptions import UnsupportedSymbolError

        raise UnsupportedSymbolError(f"Invalid symbol: {symbol}")
    return normalized


def require_default_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized not in SUPPORTED_SYMBOLS:
        from app.data.exceptions import UnsupportedSymbolError

        raise UnsupportedSymbolError(f"Symbol is not in the default index: {symbol}")
    return normalized
