from __future__ import annotations

from datetime import date, datetime, timezone

from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.normalization import optional_float, optional_int
from app.data.provider import MarketDataProvider
from app.data.providers.futu.client import FutuClient
from app.data.universe import normalize_symbol


class FutuProvider(MarketDataProvider):
    provider_name = "FUTU"

    def __init__(self, client: FutuClient):
        self.client = client

    async def connect(self) -> None:
        await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    async def health_check(self) -> bool:
        return await self.client.health_check()

    async def get_stock_quote(self, symbol: str) -> StockQuote:
        symbol = normalize_symbol(symbol)
        raw = await self.client.stock_quote(symbol)
        return StockQuote(symbol=symbol, timestamp=datetime.now(timezone.utc), price=optional_float(raw.get("price")), bid=optional_float(raw.get("bid")), ask=optional_float(raw.get("ask")), volume=optional_int(raw.get("volume")), provider=self.provider_name, delayed=raw.get("delayed"), feed="futu", price_type="bbo")

    async def get_option_chain(self, symbol: str, expiry: date | datetime | None = None) -> list[OptionContract]:
        symbol = normalize_symbol(symbol)
        rows = await self.client.option_chain(symbol, expiry)
        return [OptionContract(contract_id=f"FUTU:{row['code']}", symbol=symbol, expiry=datetime.fromisoformat(row["expiry"]).replace(tzinfo=timezone.utc), strike=optional_float(row["strike"]), option_type=row["option_type"], multiplier=100, currency="USD", exchange=None, provider=self.provider_name) for row in rows]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        raw = await self.client.option_quote(contract.contract_id.split(":", 1)[1])
        return OptionQuote(contract_id=contract.contract_id, symbol=contract.symbol, expiry=contract.expiry, strike=contract.strike, option_type=contract.option_type, timestamp=datetime.now(timezone.utc), bid=optional_float(raw.get("bid")), ask=optional_float(raw.get("ask")), last=optional_float(raw.get("last")), volume=optional_int(raw.get("volume")), open_interest=optional_int(raw.get("open_interest")), implied_volatility=optional_float(raw.get("implied_volatility")), provider=self.provider_name, delayed=raw.get("delayed"), feed="futu", price_type="bbo")
