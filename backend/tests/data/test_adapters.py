import asyncio
from datetime import datetime, timezone

import pytest

from app.data.exceptions import ProviderConfigurationError, UnsupportedSymbolError
from app.data.factory import create_provider
from app.data.provider import MarketDataProvider
from app.data.providers.futu.adapter import FutuProvider
from app.data.providers.ibkr.adapter import IBKRProvider


class FakeIBKRClient:
    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return self.connected

    async def stock_quote(self, symbol: str) -> dict:
        return {"price": 100.0, "bid": None, "ask": None, "volume": None, "delayed": False}

    async def option_chain(self, symbol: str, expiry) -> list[dict]:
        return [{"symbol": symbol, "expiry": "20260821", "strike": 100.0, "option_type": "C"}]

    async def option_quote(self, symbol: str, expiry: str, strike: float, option_type: str) -> dict:
        return {"bid": 1.0, "ask": 1.2, "last": 1.1, "volume": None, "open_interest": None, "implied_volatility": None, "delayed": False}


class FakeFutuClient(FakeIBKRClient):
    async def option_chain(self, symbol: str, expiry) -> list[dict]:
        return [{"code": "US.NVDA260821C00100000", "expiry": "2026-08-21", "strike": 100.0, "option_type": "CALL"}]

    async def option_quote(self, code: str) -> dict:
        return {"bid": 1.0, "ask": 1.2, "last": 1.1, "volume": None, "open_interest": None, "implied_volatility": None, "delayed": True}


def test_adapters_normalize_mocked_sdk_payloads() -> None:
    async def check() -> None:
        ibkr = IBKRProvider(FakeIBKRClient())
        futu = FutuProvider(FakeFutuClient())
        for provider, expected_prefix in ((ibkr, "IBKR:"), (futu, "FUTU:")):
            assert isinstance(provider, MarketDataProvider)
            await provider.connect()
            stock = await provider.get_stock_quote("nvda")
            contract = (await provider.get_option_chain("NVDA"))[0]
            quote = await provider.get_option_quote(contract)
            assert stock.symbol == "NVDA"
            assert contract.contract_id.startswith(expected_prefix)
            assert quote.bid == 1.0
            assert quote.volume is None
            await provider.disconnect()
    asyncio.run(check())


def test_unsupported_symbol_and_factory_configuration_fail_predictably() -> None:
    async def check() -> None:
        with pytest.raises(UnsupportedSymbolError):
            await IBKRProvider(FakeIBKRClient()).get_stock_quote("TSLA")
    asyncio.run(check())
    assert isinstance(create_provider("IBKR"), MarketDataProvider)
    assert isinstance(create_provider("FUTU"), MarketDataProvider)
    with pytest.raises(ProviderConfigurationError):
        create_provider("unsupported")
