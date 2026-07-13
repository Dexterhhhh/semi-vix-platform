"""Provider-independent, JSON-safe market-data models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _MarketDataModel(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    @staticmethod
    def _finite(value: Optional[float], field_name: str) -> Optional[float]:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{field_name} must be a finite non-negative number")
        return number

    @field_validator("symbol", "provider", mode="before", check_fields=False)
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if not normalized:
            raise ValueError("identifier must not be empty")
        return normalized

    @field_validator("timestamp", "expiry", mode="after", check_fields=False)
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)


class StockQuote(_MarketDataModel):
    symbol: str
    timestamp: datetime
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[int] = Field(default=None, ge=0)
    provider: str
    delayed: Optional[bool] = None

    @field_validator("price", "bid", "ask", mode="after")
    @classmethod
    def validate_quote_number(cls, value: Optional[float], info) -> Optional[float]:
        return cls._finite(value, info.field_name)

    @model_validator(mode="after")
    def validate_spread(self) -> "StockQuote":
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        return self


class OptionContract(_MarketDataModel):
    contract_id: str = Field(min_length=3, max_length=256)
    symbol: str
    expiry: datetime
    strike: float
    option_type: Literal["C", "P"]
    multiplier: Optional[int] = Field(default=None, ge=1)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    exchange: Optional[str] = Field(default=None, max_length=32)
    provider: str

    @field_validator("option_type", mode="before")
    @classmethod
    def normalize_option_type(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        mapping = {"CALL": "C", "PUT": "P", "C": "C", "P": "P"}
        if normalized not in mapping:
            raise ValueError("option_type must be CALL/C or PUT/P")
        return mapping[normalized]

    @field_validator("strike", mode="after")
    @classmethod
    def validate_strike(cls, value: float) -> float:
        result = cls._finite(value, "strike")
        if result is None:
            raise ValueError("strike is required")
        return result

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        normalized = str(value).strip().upper()
        if len(normalized) != 3:
            raise ValueError("currency must be a three-letter code")
        return normalized

    @model_validator(mode="after")
    def require_provider_qualified_contract_id(self) -> "OptionContract":
        if not self.contract_id.upper().startswith(f"{self.provider}:"):
            raise ValueError("contract_id must be qualified with its provider")
        return self


class OptionQuote(_MarketDataModel):
    contract_id: str = Field(min_length=3, max_length=256)
    symbol: str
    expiry: datetime
    strike: float
    option_type: Literal["C", "P"]
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = Field(default=None, ge=0)
    open_interest: Optional[int] = Field(default=None, ge=0)
    implied_volatility: Optional[float] = None
    provider: str
    delayed: Optional[bool] = None

    @field_validator("option_type", mode="before")
    @classmethod
    def normalize_option_type(cls, value: str) -> str:
        return OptionContract.normalize_option_type(value)

    @field_validator("strike", "bid", "ask", "last", "implied_volatility", mode="after")
    @classmethod
    def validate_quote_number(cls, value: Optional[float], info) -> Optional[float]:
        return cls._finite(value, info.field_name)

    @model_validator(mode="after")
    def validate_quote(self) -> "OptionQuote":
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid cannot exceed ask")
        if not self.contract_id.upper().startswith(f"{self.provider}:"):
            raise ValueError("contract_id must be qualified with its provider")
        return self
