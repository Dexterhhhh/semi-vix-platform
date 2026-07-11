class ProviderError(RuntimeError):
    """Base exception for read-only market data provider failures."""


class ProviderUnavailableError(ProviderError):
    """Provider gateway, SDK, or subscription is unavailable."""


class ProviderConfigurationError(ProviderError):
    """Provider configuration is unsupported or invalid."""


class ProviderPermissionError(ProviderError):
    """The provider rejected a read-only market-data request."""


class UnsupportedSymbolError(ProviderError):
    """The requested underlying is outside the supported Phase 2 universe."""


class OptionChainUnavailableError(ProviderError):
    """No eligible option contracts are available for an underlying."""


class PersistenceError(RuntimeError):
    """Normalized market data could not be persisted safely."""
