from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from app.data.models import OptionQuote


VALUATION_TIME = datetime(2026, 1, 2, 16, 0, tzinfo=timezone.utc)


def make_chain(symbol: str, expiry: datetime, scale: float = 1.0) -> list[OptionQuote]:
    source = json.loads((Path(__file__).parent / "fixtures" / "sample_option_chain.json").read_text())
    quotes = []
    for row in source:
        option_type = row["option_type"]
        strike = row["strike"]
        quotes.append(OptionQuote(contract_id=f"TEST:{symbol}:{expiry.date()}:{strike}:{option_type}", symbol=symbol, expiry=expiry, strike=strike, option_type=option_type, timestamp=VALUATION_TIME, bid=row["bid"] * scale, ask=row["ask"] * scale, last=None, volume=10, open_interest=20, implied_volatility=None, provider="TEST"))
    return quotes


def two_expiry_chain(symbol: str) -> list[OptionQuote]:
    return make_chain(symbol, VALUATION_TIME + timedelta(days=20), 1.0) + make_chain(symbol, VALUATION_TIME + timedelta(days=40), 1.2)
