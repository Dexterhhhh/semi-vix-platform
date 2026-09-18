from datetime import date, datetime, timedelta, timezone

import pytest

from app.data.models import OptionQuote
from app.services.svix_calculator import _aligned_returns, _quote_identity


def test_returns_are_aligned_by_trading_date_before_differencing() -> None:
    start = date(2025, 1, 1)
    path = {start + timedelta(days=index): 100.0 + index for index in range(270)}
    missing = dict(path)
    missing.pop(start + timedelta(days=260))
    returns = _aligned_returns({"A": path, "B": missing}, {"A", "B"})
    assert returns["A"] == pytest.approx(returns["B"])
    assert len(returns["A"]) == 268


def test_quote_identity_rejects_mixed_collection_batches() -> None:
    timestamp = datetime(2026, 1, 2, 16, tzinfo=timezone.utc)
    base = OptionQuote(contract_id="TEST:A", symbol="A", expiry=timestamp + timedelta(days=30), strike=100, option_type="C", timestamp=timestamp, bid=1, ask=2, provider="TEST", feed="bbo", price_type="bbo", batch_id="one")
    mixed = base.model_copy(update={"contract_id": "TEST:B", "option_type": "P", "batch_id": "two"})
    with pytest.raises(ValueError, match="Mixed collection batches"):
        _quote_identity({"A": [base, mixed]})
