from __future__ import annotations

from app.config import get_settings
from app.data.exceptions import ProviderConfigurationError
from app.data.provider import MarketDataProvider
from app.data.providers.futu.adapter import FutuProvider
from app.data.providers.futu.client import FutuClient
from app.data.providers.ibkr.adapter import IBKRProvider
from app.data.providers.ibkr.client import IBKRClient


def create_provider(provider_name: str | None = None) -> MarketDataProvider:
    settings = get_settings()
    provider = (provider_name or settings.data_provider).upper()
    if provider == "IBKR":
        return IBKRProvider(IBKRClient(settings.ibkr_host, settings.ibkr_port, settings.ibkr_client_id))
    if provider == "FUTU":
        return FutuProvider(FutuClient(settings.futu_host, settings.futu_port))
    raise ProviderConfigurationError(f"Unsupported DATA_PROVIDER: {provider}")
