import asyncio
from datetime import datetime, timezone

from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.provider import MarketDataProvider
from app.database.database import Base, SessionLocal, engine
from app.database.models import OptionSnapshot, StockSnapshot
from app.services.market_collector import collect_option_snapshot


class PartiallyAvailableProvider(MarketDataProvider):
    provider_name = "FAKE"

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def health_check(self) -> bool:
        return self.connected

    async def get_stock_quote(self, symbol: str) -> StockQuote:
        if symbol == "SKHY":
            raise RuntimeError("chain unavailable")
        return StockQuote(symbol=symbol, timestamp=datetime.now(timezone.utc), price=100.0, provider=self.provider_name)

    async def get_option_chain(self, symbol: str, expiry=None) -> list[OptionContract]:
        timestamp = datetime.now(timezone.utc)
        return [OptionContract(contract_id=f"FAKE:{symbol}:C", symbol=symbol, expiry=timestamp, strike=100.0, option_type="C", provider=self.provider_name)]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        return OptionQuote(contract_id=contract.contract_id, symbol=contract.symbol, expiry=contract.expiry, strike=contract.strike, option_type=contract.option_type, timestamp=datetime.now(timezone.utc), bid=1.0, ask=1.2, provider=self.provider_name)


def test_collector_commits_available_symbols_when_one_symbol_fails() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    database = SessionLocal()
    try:
        summary = asyncio.run(collect_option_snapshot(("NVDA", "SKHY", "AMD"), database, provider=PartiallyAvailableProvider()))
        assert summary["symbols_succeeded"] == 2
        assert summary["symbols_failed"] == 1
        assert summary["stock_quotes_saved"] == 2
        assert summary["option_quotes_saved"] == 2
        assert summary["errors"][0]["symbol"] == "SKHY"
        assert database.query(StockSnapshot).count() == 2
        assert database.query(OptionSnapshot).count() == 2
    finally:
        database.close()
