import asyncio
from datetime import datetime, timezone
from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.provider import MarketDataProvider


class FakeProvider(MarketDataProvider):
    provider_name = "FAKE"

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return self.connected

    async def get_stock_quote(self, symbol: str) -> StockQuote:
        return StockQuote(symbol, datetime.now(timezone.utc), 100.0, 99.0, 101.0, 10)

    async def get_option_chain(self, symbol: str, expiry=None) -> list[OptionContract]:
        expiry = expiry or datetime(2026, 8, 21, tzinfo=timezone.utc)
        return [OptionContract(symbol, expiry, 100.0, "C", "fake-contract")]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        return OptionQuote(contract.contract_id, contract.symbol, contract.expiry, contract.strike, contract.option_type, 4.0, 4.2, 4.1, 10, 20, 0.31)


def test_provider_interface_contract() -> None:
    async def check() -> None:
        provider = FakeProvider()
        await provider.connect()
        assert await provider.health_check()
        contract = (await provider.get_option_chain("NVDA"))[0]
        assert (await provider.get_option_quote(contract)).implied_volatility == 0.31
        await provider.disconnect()
        assert not await provider.health_check()
    asyncio.run(check())
