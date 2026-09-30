from __future__ import annotations

from app.config import get_settings
from app.data.exceptions import ProviderConfigurationError
from app.data.provider import MarketDataProvider
from app.data.vendor_factory import create_vendor_provider
from app.data.providers.alpaca.adapter import AlpacaProvider
from app.data.providers.alpaca.client import AlpacaClient


def create_provider(
    provider_name: str | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    client_id: int | None = None,
    api_key: str | None = None,
    secret: str | None = None,
    data_feed: str | None = None,
) -> MarketDataProvider:
    settings = get_settings()
    provider = (provider_name or settings.data_provider).upper()
    if provider in {"IBKR", "FUTU"}:
        return create_vendor_provider(provider, host=host, port=port, client_id=client_id)
    if provider == "ALPACA":
        if not api_key or not secret:
            raise ProviderConfigurationError("Alpaca API key and secret are required")
        return AlpacaProvider(
            AlpacaClient(
                api_key=api_key,
                secret=secret,
                feed=data_feed or settings.alpaca_feed,
                # Credentials must never be forwarded to a dashboard-supplied URL.
                base_url=settings.alpaca_base_url,
            )
        )
    raise ProviderConfigurationError(f"Unsupported DATA_PROVIDER: {provider}")
