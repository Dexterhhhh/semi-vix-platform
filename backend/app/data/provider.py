from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from app.data.models import OptionContract, OptionQuote, StockQuote


class MarketDataProvider(ABC):
    """Read-only, asynchronous provider contract. Order APIs are deliberately absent."""

    provider_name: str

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def get_stock_quote(self, symbol: str) -> StockQuote: ...

    @abstractmethod
    async def get_option_chain(self, symbol: str, expiry: date | datetime | None = None) -> list[OptionContract]: ...

    @abstractmethod
    async def get_option_quote(self, contract: OptionContract) -> OptionQuote: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
