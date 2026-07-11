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
        return StockQuote(symbol=symbol, timestamp=datetime.now(timezone.utc), price=100.0, bid=99.0, ask=101.0, volume=10, provider=self.provider_name)

    async def get_option_chain(self, symbol: str, expiry=None) -> list[OptionContract]:
        expiry = expiry or datetime(2026, 8, 21, tzinfo=timezone.utc)
        return [OptionContract(contract_id="FAKE:fake-contract", symbol=symbol, expiry=expiry, strike=100.0, option_type="C", provider=self.provider_name)]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        return OptionQuote(contract_id=contract.contract_id, symbol=contract.symbol, expiry=contract.expiry, strike=contract.strike, option_type=contract.option_type, timestamp=datetime.now(timezone.utc), bid=4.0, ask=4.2, last=4.1, volume=10, open_interest=20, implied_volatility=0.31, provider=self.provider_name)


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
