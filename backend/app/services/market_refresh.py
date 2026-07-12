"""Worker-only market refresh entry point with no FastAPI dependency."""

from __future__ import annotations

import asyncio
import json

from app.database.database import SessionLocal
from app.database.models import SystemSettings
from app.services.market_collector import DEFAULT_SYMBOLS, collect_option_snapshot


def refresh_market_data() -> dict[str, object]:
    database = SessionLocal()
    try:
        selection = database.query(SystemSettings).filter_by(key="selected_symbols").first()
        symbols = tuple(json.loads(selection.value)) if selection else DEFAULT_SYMBOLS
        return asyncio.run(collect_option_snapshot(symbols, database))
    finally:
        database.close()
