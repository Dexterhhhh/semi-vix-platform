"""Canonical Phase 2 underlyings shared by every market-data provider."""

DEFAULT_SYMBOLS = ("SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO")
SUPPORTED_SYMBOLS = frozenset(DEFAULT_SYMBOLS)


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized not in SUPPORTED_SYMBOLS:
        from app.data.exceptions import UnsupportedSymbolError

        raise UnsupportedSymbolError(f"Unsupported symbol: {symbol}")
    return normalized
