class ProviderError(RuntimeError):
    """Base exception for read-only market data provider failures."""


class ProviderUnavailableError(ProviderError):
    """Provider gateway, SDK, or subscription is unavailable."""


class UnsupportedSymbolError(ProviderError):
    """The requested underlying is outside the supported Phase 2 universe."""
