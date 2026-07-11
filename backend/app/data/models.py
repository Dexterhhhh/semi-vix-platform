from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class StockQuote:
    symbol: str
    timestamp: datetime
    price: Optional[float]
    bid: Optional[float]
    ask: Optional[float]
    volume: Optional[int]


@dataclass(frozen=True)
class OptionContract:
    symbol: str
    expiry: datetime
    strike: float
    option_type: str
    contract_id: str


@dataclass(frozen=True)
class OptionQuote:
    contract_id: str
    symbol: str
    expiry: datetime
    strike: float
    option_type: str
    bid: Optional[float]
    ask: Optional[float]
    last: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    implied_volatility: Optional[float]
