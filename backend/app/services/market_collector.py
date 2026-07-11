from __future__ import annotations

import logging
from collections.abc import Iterable
from sqlalchemy.orm import Session
from app.data.factory import create_provider
from app.data.provider import MarketDataProvider
from app.data.storage.option_repository import OptionRepository
from app.data.storage.quote_repository import QuoteRepository

logger = logging.getLogger(__name__)
DEFAULT_SYMBOLS = ("SOXX", "MU", "SKHY", "NVDA", "AMD", "AVGO")


async def collect_option_snapshot(symbols: Iterable[str], database: Session, provider: MarketDataProvider | None = None) -> dict[str, int]:
    """Collect read-only underlying/option quotes, normalize them, and commit snapshots."""
    market_provider = provider or create_provider()
    stock_repository, option_repository = QuoteRepository(database), OptionRepository(database)
    stock_count = option_count = 0
    try:
        await market_provider.connect()
        for symbol in symbols:
            stock_repository.save(await market_provider.get_stock_quote(symbol))
            stock_count += 1
            for contract in await market_provider.get_option_chain(symbol):
                option_repository.save(market_provider.provider_name, await market_provider.get_option_quote(contract))
                option_count += 1
        database.commit()
        return {"stocks": stock_count, "options": option_count}
    except Exception:
        database.rollback()
        logger.exception("Market data collection failed")
        raise
    finally:
        await market_provider.disconnect()
