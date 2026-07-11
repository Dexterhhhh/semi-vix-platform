class SVIXError(RuntimeError):
    """Base error for deterministic SVIX calculations."""


class InsufficientOptionData(SVIXError):
    """A chain lacks valid strikes or put-call pairs."""


class InvalidForwardPrice(SVIXError):
    """Put-call parity cannot produce a positive, finite forward price."""


class MissingExpiry(SVIXError):
    """The requested 30-day term cannot be bracketed by valid expiries."""


class InvalidVariance(SVIXError):
    """Variance replication produced an invalid result."""


class InsufficientCorrelationData(SVIXError):
    """Historical return series cannot support the required correlation windows."""
