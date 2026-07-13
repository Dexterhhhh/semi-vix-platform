"""Alpaca historical proxy-data backfill for asynchronous SVIX jobs.

Alpaca exposes historical option trades/bars but no historical option BBO
endpoint. Daily option closes are therefore persisted as equal bid/ask proxy
prices and marked ``delayed=True`` so the engine discounts result quality.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.data.credentials import decrypt_credential
from app.data.exceptions import ProviderPermissionError, ProviderUnavailableError
from app.data.models import OptionQuote, StockQuote
from app.data.providers.alpaca.client import parse_occ_symbol
from app.data.storage.option_repository import OptionRepository
from app.data.storage.quote_repository import QuoteRepository
from app.database.models import OptionSnapshot, ProviderCredential, StockSnapshot

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[int, str], None]


def _chunks(values: list[str], size: int = 100) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index:index + size]


def _month_windows(start: date, end: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        windows.append((max(start, cursor), min(end, next_month - timedelta(days=1))))
        cursor = next_month
    return windows


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _utc_midnight(value: date) -> str:
    """Use RFC 3339 so Alpaca does not treat a date-only end as live OPRA data."""
    return datetime.combine(value, time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


class AlpacaHistoricalBackfill:
    def __init__(self, database: Session, credential: ProviderCredential):
        if not credential.api_key_encrypted or not credential.secret_encrypted:
            raise ProviderPermissionError("Alpaca API credentials are missing")
        self.database = database
        self.headers = {
            "APCA-API-KEY-ID": decrypt_credential(credential.api_key_encrypted),
            "APCA-API-SECRET-KEY": decrypt_credential(credential.secret_encrypted),
        }
        self.stock_feed = "sip" if (credential.data_feed or "indicative").lower() == "opra" else "iex"
        self.options = OptionRepository(database)
        self.stocks = QuoteRepository(database)

    async def _get(self, client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(6):
            try:
                response = await client.get(url, params=params)
                if response.status_code in {401, 403}:
                    try:
                        message = str(response.json().get("message") or "")
                    except (ValueError, AttributeError):
                        message = ""
                    if "OPRA" in message.upper():
                        raise ProviderPermissionError("Alpaca rejected recent OPRA data; use delayed historical timestamps")
                    raise ProviderPermissionError("Alpaca rejected historical-data access")
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt == 5:
                        response.raise_for_status()
                    retry_after = min(60.0, float(response.headers.get("retry-after", 2 ** attempt)))
                    await asyncio.sleep(retry_after)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("unexpected Alpaca payload")
                return payload
            except ProviderPermissionError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                if attempt == 5:
                    raise ProviderUnavailableError("Alpaca historical-data request failed") from exc
                await asyncio.sleep(min(10.0, 2 ** attempt))
        raise ProviderUnavailableError("Alpaca historical-data request failed")

    async def _stock_bars(self, client: httpx.AsyncClient, symbols: tuple[str, ...], start: date, end: date) -> dict[str, list[dict[str, Any]]]:
        params: dict[str, Any] = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": _utc_midnight(start), "end": _utc_midnight(end + timedelta(days=1)), "feed": self.stock_feed, "limit": 10000}
        collected: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for _ in range(100):
            payload = await self._get(client, "https://data.alpaca.markets/v2/stocks/bars", params)
            for symbol, bars in (payload.get("bars") or {}).items():
                collected[symbol].extend(bars or [])
            token = payload.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        return collected

    async def _contracts(self, client: httpx.AsyncClient, symbol: str, expiration_start: date, expiration_end: date, reference_price: float) -> list[str]:
        contracts: dict[str, dict[str, Any]] = {}
        for status in ("active", "inactive"):
            params: dict[str, Any] = {
                "underlying_symbols": symbol,
                "status": status,
                "expiration_date_gte": expiration_start.isoformat(),
                "expiration_date_lte": expiration_end.isoformat(),
                "strike_price_gte": round(reference_price * 0.5, 2),
                "strike_price_lte": round(reference_price * 1.5, 2),
                "limit": 10000,
            }
            for _ in range(20):
                payload = await self._get(client, "https://paper-api.alpaca.markets/v2/options/contracts", params)
                for item in payload.get("option_contracts") or []:
                    if item.get("symbol"):
                        contracts[item["symbol"]] = item
                token = payload.get("next_page_token") or payload.get("page_token")
                if not token:
                    break
                params["page_token"] = token

        by_expiry: dict[date, dict[float, list[str]]] = defaultdict(lambda: defaultdict(list))
        for contract_symbol in contracts:
            try:
                parsed = parse_occ_symbol(contract_symbol)
            except ValueError:
                continue
            by_expiry[parsed["expiry"].date()][parsed["strike"]].append(contract_symbol)
        selected: list[str] = []
        for strikes in by_expiry.values():
            nearest = sorted(strikes, key=lambda strike: abs(strike - reference_price))[:40]
            for strike in nearest:
                selected.extend(strikes[strike])
        return selected

    async def _option_bars(self, client: httpx.AsyncClient, symbols: list[str], start: date, end: date) -> dict[str, list[dict[str, Any]]]:
        collected: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for batch in _chunks(symbols):
            # The option-bars endpoint rejects ``feed=indicative``. Basic/free
            # accounts can still read delayed history, but date-only ``end``
            # values may be interpreted as including the latest OPRA window.
            params: dict[str, Any] = {"symbols": ",".join(batch), "timeframe": "1Day", "start": _utc_midnight(start), "end": _utc_midnight(end + timedelta(days=1)), "limit": 10000}
            for _ in range(100):
                payload = await self._get(client, "https://data.alpaca.markets/v1beta1/options/bars", params)
                for symbol, bars in (payload.get("bars") or {}).items():
                    collected[symbol].extend(bars or [])
                token = payload.get("next_page_token")
                if not token:
                    break
                params["page_token"] = token
        return collected

    def _save_stock_bars(self, bars_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, dict[date, float]]:
        prices: dict[str, dict[date, float]] = defaultdict(dict)
        if not bars_by_symbol:
            return prices
        timestamps = [_parse_timestamp(bar["t"]) for bars in bars_by_symbol.values() for bar in bars if bar.get("t")]
        existing = set()
        if timestamps:
            existing = {(row.symbol, row.timestamp) for row in self.database.query(StockSnapshot).filter(StockSnapshot.provider == "ALPACA", StockSnapshot.timestamp >= min(timestamps), StockSnapshot.timestamp <= max(timestamps)).all()}
        quotes: list[StockQuote] = []
        for symbol, bars in bars_by_symbol.items():
            for bar in bars:
                close = float(bar.get("c") or 0)
                if close <= 0 or not bar.get("t"):
                    continue
                timestamp = _parse_timestamp(bar["t"])
                prices[symbol][timestamp.date()] = close
                if (symbol, timestamp) not in existing:
                    quotes.append(StockQuote(symbol=symbol, timestamp=timestamp, price=close, volume=int(bar.get("v") or 0), provider="ALPACA", delayed=True))
        self.stocks.save_many(quotes)
        return prices

    def _save_option_bars(self, symbol: str, bars_by_contract: dict[str, list[dict[str, Any]]], start: date, end: date) -> int:
        existing = {(row.contract_id, row.timestamp) for row in self.database.query(OptionSnapshot).filter(OptionSnapshot.provider == "ALPACA", OptionSnapshot.symbol == symbol, OptionSnapshot.timestamp >= datetime.combine(start, time.min, tzinfo=timezone.utc), OptionSnapshot.timestamp <= datetime.combine(end, time.max, tzinfo=timezone.utc)).all()}
        quotes: list[OptionQuote] = []
        for contract_symbol, bars in bars_by_contract.items():
            try:
                contract = parse_occ_symbol(contract_symbol)
            except ValueError:
                continue
            for bar in bars:
                close = float(bar.get("c") or 0)
                if close <= 0 or not bar.get("t"):
                    continue
                timestamp = _parse_timestamp(bar["t"])
                key = (f"ALPACA:{contract_symbol}", timestamp)
                if key in existing:
                    continue
                quotes.append(OptionQuote(contract_id=key[0], symbol=symbol, expiry=contract["expiry"], strike=contract["strike"], option_type=contract["option_type"], timestamp=timestamp, bid=close, ask=close, last=close, volume=int(bar.get("v") or 0), provider="ALPACA", delayed=True))
        self.options.save_many(quotes)
        return len(quotes)

    async def run(self, start: date, end: date, symbols: tuple[str, ...], progress: ProgressCallback | None = None) -> dict[str, int]:
        completed_end = min(end, datetime.now(timezone.utc).date() - timedelta(days=1))
        if completed_end < start:
            return {"stock_rows": 0, "option_rows": 0}
        windows = _month_windows(start, completed_end)
        stock_rows = option_rows = 0
        async with httpx.AsyncClient(headers=self.headers, timeout=httpx.Timeout(30.0)) as client:
            history_start = start - timedelta(days=420)
            stock_bars = await self._stock_bars(client, symbols, history_start, completed_end)
            stock_rows = sum(len(rows) for rows in stock_bars.values())
            prices = self._save_stock_bars(stock_bars)
            self.database.commit()
            if progress:
                progress(15, "已回填标的历史日线")

            total_steps = max(1, len(windows) * len(symbols))
            completed_steps = 0
            for window_start, window_end in windows:
                for symbol in symbols:
                    month_prices = [price for day, price in prices.get(symbol, {}).items() if window_start <= day <= window_end]
                    if month_prices:
                        reference = sorted(month_prices)[len(month_prices) // 2]
                        contracts = await self._contracts(client, symbol, window_start + timedelta(days=20), window_end + timedelta(days=45), reference)
                        bars = await self._option_bars(client, contracts, window_start, window_end) if contracts else {}
                        option_rows += self._save_option_bars(symbol, bars, window_start, window_end)
                        self.database.commit()
                    completed_steps += 1
                    if progress:
                        percent = 15 + int(65 * completed_steps / total_steps)
                        progress(percent, f"回填 {window_start:%Y-%m} {symbol}")
        return {"stock_rows": stock_rows, "option_rows": option_rows}


def backfill_alpaca_history(database: Session, start: date, end: date, symbols: tuple[str, ...], progress: ProgressCallback | None = None) -> dict[str, int]:
    credential = database.query(ProviderCredential).filter_by(provider="ALPACA", enabled=True).first()
    if credential is None:
        raise ProviderPermissionError("Alpaca is not the active provider")
    return asyncio.run(AlpacaHistoricalBackfill(database, credential).run(start, end, symbols, progress))
