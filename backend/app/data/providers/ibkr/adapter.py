from datetime import datetime, timezone
from typing import Optional
from app.data.exceptions import UnsupportedSymbolError
from app.data.models import OptionContract, OptionQuote, StockQuote
from app.data.provider import MarketDataProvider
from app.data.providers.ibkr.client import IBKRClient

SUPPORTED_SYMBOLS = frozenset({"SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO"})


def _number(value: object) -> Optional[float]:
    try:
        number = float(value)
        return number if number == number else None
    except (TypeError, ValueError):
        return None


class IBKRProvider(MarketDataProvider):
    provider_name = "IBKR"

    def __init__(self, client: IBKRClient):
        self.client = client

    @staticmethod
    def _symbol(symbol: str) -> str:
        normalized = symbol.upper()
        if normalized not in SUPPORTED_SYMBOLS:
            raise UnsupportedSymbolError(f"Unsupported IBKR symbol: {symbol}")
        return normalized

    async def connect(self) -> None:
        await self.client.connect()

    async def disconnect(self) -> None:
        await self.client.disconnect()

    async def health_check(self) -> bool:
        return await self.client.health_check()

    async def get_stock_quote(self, symbol: str) -> StockQuote:
        symbol = self._symbol(symbol)
        raw = await self.client.stock_quote(symbol)
        return StockQuote(symbol, datetime.now(timezone.utc), _number(raw.get("price")), _number(raw.get("bid")), _number(raw.get("ask")), int(raw["volume"]) if raw.get("volume") else None)

    async def get_option_chain(self, symbol: str, expiry: Optional[datetime] = None) -> list[OptionContract]:
        symbol = self._symbol(symbol)
        rows = await self.client.option_chain(symbol, expiry)
        return [OptionContract(symbol, datetime.strptime(row["expiry"], "%Y%m%d").replace(tzinfo=timezone.utc), row["strike"], row["option_type"], f"{symbol}:{row['expiry']}:{row['strike']}:{row['option_type']}") for row in rows]

    async def get_option_quote(self, contract: OptionContract) -> OptionQuote:
        raw = await self.client.option_quote(contract.symbol, contract.expiry.strftime("%Y%m%d"), contract.strike, contract.option_type)
        return OptionQuote(contract.contract_id, contract.symbol, contract.expiry, contract.strike, contract.option_type, _number(raw.get("bid")), _number(raw.get("ask")), _number(raw.get("last")), int(raw["volume"]) if raw.get("volume") else None, int(raw["open_interest"]) if raw.get("open_interest") else None, _number(raw.get("implied_volatility")))
