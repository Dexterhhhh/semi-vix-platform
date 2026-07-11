from sqlalchemy.orm import Session
from app.services.market_collector import DEFAULT_SYMBOLS, collect_option_snapshot


async def collect_market_data(database: Session) -> dict[str, int]:
    """Phase 2 placeholder callable; Celery scheduling is intentionally deferred."""
    return await collect_option_snapshot(DEFAULT_SYMBOLS, database)
