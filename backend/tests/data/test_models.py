from datetime import datetime, timezone
import math

import pytest
from pydantic import ValidationError

from app.data.models import OptionContract, OptionQuote, StockQuote


def test_normalized_models_retain_provider_independent_fields() -> None:
    timestamp = datetime.now(timezone.utc)
    contract = OptionContract(contract_id="IBKR:contract-1", symbol="NVDA", expiry=timestamp, strike=120.0, option_type="CALL", multiplier=100, currency="usd", exchange="SMART", provider="ibkr")
    quote = OptionQuote(contract_id=contract.contract_id, symbol="NVDA", expiry=timestamp, strike=120.0, option_type="C", timestamp=timestamp, bid=2.0, ask=2.2, last=2.1, volume=100, open_interest=50, implied_volatility=0.45, provider="IBKR")
    stock = StockQuote(symbol="NVDA", timestamp=timestamp, price=119.5, bid=119.4, ask=119.6, volume=2000, provider="IBKR")
    assert contract.option_type == quote.option_type == "C"
    assert quote.contract_id == contract.contract_id
    assert stock.price == 119.5
    assert stock.model_dump(mode="json")["timestamp"].endswith("Z")


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "NVDA", "timestamp": datetime.now(), "price": 1.0, "provider": "IBKR"},
        {"symbol": "NVDA", "timestamp": datetime.now(timezone.utc), "bid": 2.0, "ask": 1.0, "provider": "IBKR"},
        {"symbol": "NVDA", "timestamp": datetime.now(timezone.utc), "price": math.inf, "provider": "IBKR"},
    ],
)
def test_stock_quote_rejects_malformed_market_data(payload: dict) -> None:
    with pytest.raises(ValidationError):
        StockQuote(**payload)


def test_option_contract_rejects_unqualified_identifier_and_negative_strike() -> None:
    timestamp = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        OptionContract(contract_id="contract-1", symbol="NVDA", expiry=timestamp, strike=-1.0, option_type="C", provider="IBKR")
