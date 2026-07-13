from __future__ import annotations

from datetime import date, datetime, timezone

from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.normalization import optional_float, optional_int
from app.data.provider import MarketDataProvider
from app.data.providers.alpaca.client import AlpacaClient
from app.data.universe import normalize_symbol


def _timestamp(value: object) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _spread(bid: object, ask: object) -> tuple[float | None, float | None]:
    normalized_bid = optional_float(bid)
    normalized_ask = optional_float(ask)
    if normalized_bid is not None and normalized_ask is not None and normalized_bid > normalized_ask:
        return normalized_ask, normalized_bid
    return normalized_bid, normalized_ask


class AlpacaProvider(MarketDataProvider):
    provider_name = "ALPACA"

    def __init__(self, client: AlpacaClient):
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
        bid, ask = _spread(raw.get("bid"), raw.get("ask"))
        return StockQuote(symbol=symbol, timestamp=_timestamp(raw.get("timestamp")), price=optional_float(raw.get("price")), bid=bid, ask=ask, volume=optional_int(raw.get("volume")), provider=self.provider_name, delayed=raw.get("delayed"))

    async def get_option_chain(self, symbol: str, expiry: date | datetime | None = None) -> list[OptionContract]:
        symbol = normalize_symbol(symbol)
        rows = await self.client.option_chain(symbol, expiry)
        return [OptionContract(contract_id=f"ALPACA:{row['code']}", symbol=symbol, expiry=row["expiry"], strike=row["strike"], option_type=row["option_type"], multiplier=100, currency="USD", exchange="OPRA" if self.client.feed == "opra" else "INDICATIVE", provider=self.provider_name) for row in rows]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        raw = await self.client.option_quote(contract.contract_id.split(":", 1)[1])
        bid, ask = _spread(raw.get("bid"), raw.get("ask"))
        return OptionQuote(contract_id=contract.contract_id, symbol=contract.symbol, expiry=contract.expiry, strike=contract.strike, option_type=contract.option_type, timestamp=_timestamp(raw.get("timestamp")), bid=bid, ask=ask, last=optional_float(raw.get("last")), volume=optional_int(raw.get("volume")), open_interest=optional_int(raw.get("open_interest")), implied_volatility=optional_float(raw.get("implied_volatility")), provider=self.provider_name, delayed=raw.get("delayed"))
