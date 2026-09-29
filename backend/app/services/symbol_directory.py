"""Look up listed US securities in Nasdaq Trader's public symbol directory."""

from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from io import StringIO
from time import monotonic

import httpx


DIRECTORY_URLS = (
    "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
)
CACHE_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class ListedSymbol:
    symbol: str
    name: str


class SymbolDirectoryUnavailable(Exception):
    """The directory cannot currently be fetched."""


def parse_directory(contents: str) -> dict[str, ListedSymbol]:
    """Read either Nasdaq Trader pipe-delimited directory format."""
    entries: dict[str, ListedSymbol] = {}
    reader = csv.DictReader(StringIO(contents), delimiter="|")
    for row in reader:
        symbol = (row.get("Symbol") or row.get("ACT Symbol") or "").strip().upper()
        name = (row.get("Security Name") or "").strip()
        if not symbol or not name or row.get("Test Issue", "").strip().upper() == "Y":
            continue
        if name.lower().endswith(" - common stock"):
            name = name[: -len(" - Common Stock")]
        entries[symbol] = ListedSymbol(symbol=symbol, name=name)
    return entries


_entries: dict[str, ListedSymbol] = {}
_expires_at = 0.0
_refresh_lock = asyncio.Lock()


async def lookup_symbol(symbol: str) -> ListedSymbol | None:
    global _entries, _expires_at
    if monotonic() >= _expires_at:
        async with _refresh_lock:
            if monotonic() >= _expires_at:
                try:
                    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                        responses = await asyncio.gather(*(client.get(url) for url in DIRECTORY_URLS))
                    for response in responses:
                        response.raise_for_status()
                    refreshed: dict[str, ListedSymbol] = {}
                    for response in responses:
                        refreshed.update(parse_directory(response.text))
                    if not refreshed:
                        raise ValueError("empty symbol directory")
                except (httpx.HTTPError, ValueError) as exc:
                    if not _entries:
                        raise SymbolDirectoryUnavailable from exc
                    # Keep the last complete snapshot and retry later.
                    _expires_at = monotonic() + 60
                else:
                    _entries = refreshed
                    _expires_at = monotonic() + CACHE_SECONDS
    return _entries.get(symbol.strip().upper())
