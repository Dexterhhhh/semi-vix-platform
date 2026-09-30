"""Vendor SDK construction; Alpaca uses the Go service."""

from app.config import get_settings
from app.data.exceptions import ProviderConfigurationError
from app.data.provider import MarketDataProvider
from app.data.providers.futu.adapter import FutuProvider
from app.data.providers.futu.client import FutuClient
from app.data.providers.ibkr.adapter import IBKRProvider
from app.data.providers.ibkr.client import IBKRClient


def create_vendor_provider(provider: str, *, host: str | None = None,
                           port: int | None = None, client_id: int | None = None) -> MarketDataProvider:
    settings = get_settings()
    if provider == "IBKR":
        return IBKRProvider(IBKRClient(host or settings.ibkr_host, port or settings.ibkr_port,
                                      client_id if client_id is not None else settings.ibkr_client_id))
    if provider == "FUTU":
        return FutuProvider(FutuClient(host or settings.futu_host, port or settings.futu_port))
    raise ProviderConfigurationError("Only IBKR and FUTU are handled by the SDK bridge")
