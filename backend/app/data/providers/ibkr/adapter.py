from __future__ import annotations

from datetime import date, datetime, timezone

from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.normalization import optional_float, optional_int
from app.data.provider import MarketDataProvider
from app.data.providers.ibkr.client import IBKRClient
from app.data.universe import normalize_symbol


class IBKRProvider(MarketDataProvider):
    provider_name = "IBKR"

    def __init__(self, client: IBKRClient):
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
        return StockQuote(symbol=symbol, timestamp=datetime.now(timezone.utc), price=optional_float(raw.get("price")), bid=optional_float(raw.get("bid")), ask=optional_float(raw.get("ask")), volume=optional_int(raw.get("volume")), provider=self.provider_name, delayed=raw.get("delayed"), feed="smart", price_type="bbo")

    async def get_option_chain(self, symbol: str, expiry: date | datetime | None = None) -> list[OptionContract]:
        symbol = normalize_symbol(symbol)
        rows = await self.client.option_chain(symbol, expiry)
        return [OptionContract(contract_id=f"IBKR:{symbol}:{row['expiry']}:{row['strike']}:{row['option_type']}", symbol=symbol, expiry=datetime.strptime(row["expiry"], "%Y%m%d").replace(tzinfo=timezone.utc), strike=row["strike"], option_type=row["option_type"], multiplier=100, currency="USD", exchange="SMART", provider=self.provider_name) for row in rows]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        raw = await self.client.option_quote(contract.symbol, contract.expiry.strftime("%Y%m%d"), contract.strike, contract.option_type)
        return OptionQuote(contract_id=contract.contract_id, symbol=contract.symbol, expiry=contract.expiry, strike=contract.strike, option_type=contract.option_type, timestamp=datetime.now(timezone.utc), bid=optional_float(raw.get("bid")), ask=optional_float(raw.get("ask")), last=optional_float(raw.get("last")), volume=optional_int(raw.get("volume")), open_interest=optional_int(raw.get("open_interest")), implied_volatility=optional_float(raw.get("implied_volatility")), provider=self.provider_name, delayed=raw.get("delayed"), feed="smart", price_type="bbo")
