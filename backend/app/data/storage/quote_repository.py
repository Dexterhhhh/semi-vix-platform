from sqlalchemy.orm import Session
from app.data.models import StockQuote
from app.database.models import StockSnapshot


class QuoteRepository:
    def __init__(self, database: Session):
        self.database = database

    def save(self, quote: StockQuote) -> StockSnapshot:
        snapshot = StockSnapshot(timestamp=quote.timestamp, symbol=quote.symbol, price=quote.price, bid=quote.bid, ask=quote.ask, volume=quote.volume)
        self.database.add(snapshot)
        return snapshot
