import asyncio
from datetime import datetime, timedelta, timezone

from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.provider import MarketDataProvider
from app.database.database import Base, SessionLocal, engine
from app.database.models import OptionSnapshot, StockSnapshot
from app.services.market_collector import _select_contracts, collect_option_snapshot


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


def test_contract_sampling_keeps_both_target_expiries_and_call_put_pairs() -> None:
    now = datetime.now(timezone.utc)
    contracts = [
        OptionContract(contract_id=f"FAKE:NVDA:{days}:{strike}:{right}", symbol="NVDA", expiry=now + timedelta(days=days), strike=float(strike), option_type=right, provider="FAKE")
        for days in (20, 40, 180)
        for strike in range(50, 151)
        for right in ("C", "P")
    ]
    selected = _select_contracts(contracts, 100.0, 120)
    assert {round((item.expiry - now).total_seconds() / 86400) for item in selected} == {20, 40}
    assert len(selected) == 120
    assert {(item.expiry, item.strike) for item in selected if item.option_type == "C"} == {(item.expiry, item.strike) for item in selected if item.option_type == "P"}
