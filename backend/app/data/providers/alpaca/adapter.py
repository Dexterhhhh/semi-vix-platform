from __future__ import annotations

from datetime import date, datetime, timezone

from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.normalization import optional_float, optional_int
from app.data.provider import MarketDataProvider
from app.data.providers.alpaca.client import AlpacaClient
from app.data.universe import normalize_symbol


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    raise ValueError("Market timestamp is missing or invalid")


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return _timestamp(value)
    except ValueError:
        return None


def _spread(bid: object, ask: object) -> tuple[float | None, float | None]:
    normalized_bid = optional_float(bid)
    normalized_ask = optional_float(ask)
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
        trade_at = _optional_timestamp(raw.get("trade_timestamp"))
        quote_at = _optional_timestamp(raw.get("quote_timestamp", raw.get("timestamp")))
        if bid is not None and ask is not None and bid > ask:
            bid, ask = None, None
        timestamp = quote_at or trade_at
        if timestamp is None:
            raise ValueError("Stock market timestamp is missing")
        return StockQuote(symbol=symbol, timestamp=timestamp, price=optional_float(raw.get("price")), bid=bid, ask=ask, volume=optional_int(raw.get("volume")), provider=self.provider_name, delayed=raw.get("delayed"), feed=self.client.feed, price_type="trade" if trade_at else "bbo", trade_timestamp=trade_at)

    async def get_option_chain(self, symbol: str, expiry: date | datetime | None = None) -> list[OptionContract]:
        symbol = normalize_symbol(symbol)
        rows = await self.client.option_chain(symbol, expiry)
        return [OptionContract(contract_id=f"ALPACA:{row['code']}", symbol=symbol, expiry=row["expiry"], strike=row["strike"], option_type=row["option_type"], multiplier=100, currency="USD", exchange="OPRA" if self.client.feed == "opra" else "INDICATIVE", provider=self.provider_name) for row in rows]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        raw = await self.client.option_quote(contract.contract_id.split(":", 1)[1])
        bid, ask = _spread(raw.get("bid"), raw.get("ask"))
        price_type = "bbo" if self.client.feed.lower() == "opra" else "indicative_quote"
        return OptionQuote(contract_id=contract.contract_id, symbol=contract.symbol, expiry=contract.expiry, strike=contract.strike, option_type=contract.option_type, timestamp=_timestamp(raw.get("quote_timestamp", raw.get("timestamp"))), bid=bid, ask=ask, last=optional_float(raw.get("last")), volume=optional_int(raw.get("volume")), open_interest=optional_int(raw.get("open_interest")), implied_volatility=optional_float(raw.get("implied_volatility")), provider=self.provider_name, delayed=raw.get("delayed"), feed=self.client.feed, price_type=price_type, trade_timestamp=_optional_timestamp(raw.get("trade_timestamp")))
