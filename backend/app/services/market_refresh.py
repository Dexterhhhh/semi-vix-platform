"""Worker-only market refresh entry point with no FastAPI dependency."""

from __future__ import annotations

import asyncio
import json

from app.database.database import SessionLocal
from app.database.models import SystemSettings
from app.services.market_collector import DEFAULT_SYMBOLS, collect_option_snapshot
from app.services.custom_index import custom_symbols


def refresh_market_data() -> dict[str, object]:
    database = SessionLocal()
    try:
        selection = database.query(SystemSettings).filter_by(key="selected_symbols").first()
        configured = tuple(json.loads(selection.value)) if selection else DEFAULT_SYMBOLS
        symbols = tuple(dict.fromkeys((*configured, *custom_symbols(database))))
        return asyncio.run(collect_option_snapshot(symbols, database))
    finally:
        database.close()
