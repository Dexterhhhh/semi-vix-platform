"""Read-only Alpaca Market Data client.

The client never imports or calls Alpaca trading endpoints. Option-chain
snapshots are cached so the provider abstraction does not turn one chain fetch
into hundreds of duplicate HTTP requests.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any, Literal

import httpx

from app.data.exceptions import ProviderPermissionError, ProviderUnavailableError

AlpacaFeed = Literal["indicative", "opra"]
_OCC_SYMBOL = re.compile(r"^(?P<root>[A-Z0-9.]{1,6})(?P<date>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")


def parse_occ_symbol(symbol: str) -> dict[str, Any]:
    match = _OCC_SYMBOL.fullmatch(symbol.upper())
    if match is None:
        raise ValueError("invalid OCC option symbol")
    # OCC symbols contain only a date. Use the end of the regular US session
    # instead of UTC midnight so expiry-day daily bars are not already expired.
    expiry_date = datetime.strptime(match.group("date"), "%y%m%d").date()
    expiry = datetime.combine(expiry_date, time(21, 0), tzinfo=timezone.utc)
    return {
        "code": symbol.upper(),
        "expiry": expiry,
        "strike": int(match.group("strike")) / 1000,
        "option_type": match.group("right"),
    }


class AlpacaClient:
    def __init__(self, api_key: str, secret: str, feed: str = "indicative", base_url: str = "https://data.alpaca.markets"):
        normalized_feed = feed.strip().lower()
        if normalized_feed not in {"indicative", "opra"}:
            raise ValueError("Alpaca feed must be indicative or opra")
        self.api_key = api_key
        self.secret = secret
        self.feed: AlpacaFeed = normalized_feed  # type: ignore[assignment]
        self.base_url = base_url.rstrip("/")
        self._http: httpx.AsyncClient | None = None
        self._option_snapshots: dict[str, dict[str, Any]] = {}
        self._underlying_prices: dict[str, float] = {}

    async def connect(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"APCA-API-KEY-ID": self.api_key, "APCA-API-SECRET-KEY": self.secret},
                timeout=httpx.Timeout(12.0),
            )

    async def disconnect(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        self._http = None
        self._option_snapshots.clear()
        self._underlying_prices.clear()

    async def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._http is None:
            raise ProviderUnavailableError("Alpaca client is not connected")
        try:
            response = await self._http.get(path, params=params)
            if response.status_code in {401, 403}:
                raise ProviderPermissionError("Alpaca credentials or market-data subscription were rejected")
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("unexpected response payload")
            return payload
        except ProviderPermissionError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("Alpaca market-data request failed") from exc

    async def health_check(self) -> bool:
        stock_feed = "sip" if self.feed == "opra" else "iex"
        await self._request("/v2/stocks/SPY/snapshot", {"feed": stock_feed})
        return True

    async def stock_quote(self, symbol: str) -> dict[str, Any]:
        stock_feed = "sip" if self.feed == "opra" else "iex"
        payload = await self._request(f"/v2/stocks/{symbol}/snapshot", {"feed": stock_feed})
        quote = payload.get("latestQuote") or {}
        trade = payload.get("latestTrade") or {}
        daily = payload.get("dailyBar") or {}
        result = {
            "price": trade.get("p"),
            "bid": quote.get("bp"),
            "ask": quote.get("ap"),
            "volume": daily.get("v"),
            "timestamp": quote.get("t") or trade.get("t"),
            "delayed": self.feed == "indicative",
        }
        if isinstance(result["price"], (int, float)) and result["price"] > 0:
            self._underlying_prices[symbol.upper()] = float(result["price"])
        return result

    def _prioritize_chain(self, symbol: str, rows: list[dict[str, Any]], target: date | None) -> list[dict[str, Any]]:
        if target is None and rows:
            target = datetime.now(timezone.utc).date() + timedelta(days=30)
            expiries = sorted({row["expiry"].date() for row in rows if row["expiry"].date() > datetime.now(timezone.utc).date()})
            lower = max((item for item in expiries if item <= target), default=None)
            upper = min((item for item in expiries if item >= target), default=None)
            selected = [item for item in (lower, upper) if item is not None]
            if len(set(selected)) < 2:
                adjacent = sorted(expiries, key=lambda item: abs((item - target).days))[:2]
                selected = adjacent
            selected_set = set(selected)
            rows = [row for row in rows if row["expiry"].date() in selected_set]
        reference = self._underlying_prices.get(symbol.upper())
        if reference is None and rows:
            strikes = sorted(row["strike"] for row in rows)
            reference = strikes[len(strikes) // 2]
        reference = reference or 0.0
        return sorted(rows, key=lambda row: (abs(row["strike"] - reference), row["expiry"], row["option_type"]))

    async def option_chain(self, symbol: str, expiry: date | datetime | None) -> list[dict[str, Any]]:
        target = expiry.date() if isinstance(expiry, datetime) else expiry
        params: dict[str, Any] = {"feed": self.feed, "limit": 1000}
        if target is not None:
            params["expiration_date"] = target.isoformat()
        else:
            today = datetime.now(timezone.utc).date()
            params["expiration_date_gte"] = (today + timedelta(days=20)).isoformat()
            params["expiration_date_lte"] = (today + timedelta(days=45)).isoformat()
        rows: list[dict[str, Any]] = []
        page_token: str | None = None
        for _ in range(10):
            if page_token:
                params["page_token"] = page_token
            payload = await self._request(f"/v1beta1/options/snapshots/{symbol}", params)
            snapshots = payload.get("snapshots") or {}
            if not isinstance(snapshots, dict):
                raise ProviderUnavailableError("Alpaca returned an invalid option chain")
            for contract_symbol, snapshot in snapshots.items():
                try:
                    parsed = parse_occ_symbol(contract_symbol)
                except ValueError:
                    continue
                if parsed["code"][:-15] != symbol.upper() or (target and parsed["expiry"].date() != target):
                    continue
                self._option_snapshots[parsed["code"]] = snapshot if isinstance(snapshot, dict) else {}
                rows.append(parsed)
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        return self._prioritize_chain(symbol, rows, target)

    async def option_quote(self, code: str) -> dict[str, Any]:
        snapshot = self._option_snapshots.get(code)
        if snapshot is None:
            payload = await self._request("/v1beta1/options/snapshots", {"symbols": code, "feed": self.feed})
            snapshot = (payload.get("snapshots") or {}).get(code)
        if not isinstance(snapshot, dict):
            raise ProviderUnavailableError("Alpaca option snapshot is unavailable")
        quote = snapshot.get("latestQuote") or {}
        trade = snapshot.get("latestTrade") or {}
        daily = snapshot.get("dailyBar") or {}
        return {
            "bid": quote.get("bp"),
            "ask": quote.get("ap"),
            "last": trade.get("p"),
            "volume": daily.get("v"),
            "open_interest": snapshot.get("openInterest"),
            "implied_volatility": snapshot.get("impliedVolatility"),
            "timestamp": quote.get("t") or trade.get("t"),
            "delayed": self.feed == "indicative",
        }
