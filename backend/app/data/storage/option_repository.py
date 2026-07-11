from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.data.models import OptionQuote
from app.database.models import OptionSnapshot


class OptionRepository:
    def __init__(self, database: Session):
        self.database = database

    def save(self, provider: str, quote: OptionQuote) -> OptionSnapshot:
        snapshot = OptionSnapshot(timestamp=datetime.now(timezone.utc), provider=provider, symbol=quote.symbol, expiry=quote.expiry, strike=quote.strike, option_type=quote.option_type, bid=quote.bid, ask=quote.ask, last=quote.last, volume=quote.volume, open_interest=quote.open_interest, implied_volatility=quote.implied_volatility)
        self.database.add(snapshot)
        return snapshot
