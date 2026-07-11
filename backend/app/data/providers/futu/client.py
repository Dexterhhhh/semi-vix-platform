"""Read-only Futu OpenD quotation client.

Only ``OpenQuoteContext`` is imported.  Trade contexts and order APIs are not
part of this module or its dependency boundary.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

from app.data.exceptions import ProviderUnavailableError


class FutuClient:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._context: Any = None
        self._operation_lock = None

    async def _run(self, function, *args):
        if self._operation_lock is None:
            self._operation_lock = asyncio.Lock()
        async with self._operation_lock:
            return await asyncio.to_thread(function, *args)

    def _connect_sync(self) -> None:
        if self._context is not None:
            return
        try:
            from futu import OpenQuoteContext

            self._context = OpenQuoteContext(host=self.host, port=self.port)
        except Exception as exc:
            self._context = None
            raise ProviderUnavailableError("Futu OpenD connection failed") from exc

    async def connect(self) -> None:
        await self._run(self._connect_sync)

    def _disconnect_sync(self) -> None:
        if self._context is not None:
            self._context.close()
        self._context = None

    async def disconnect(self) -> None:
        await self._run(self._disconnect_sync)

    def _health_check_sync(self) -> bool:
        if self._context is None:
            return False
        try:
            from futu import RET_OK

            result, _ = self._context.get_global_state()
            return result == RET_OK
        except Exception:
            return False

    async def health_check(self) -> bool:
        return await self._run(self._health_check_sync)

    def _require_context(self) -> Any:
        if self._context is None:
            raise ProviderUnavailableError("Futu OpenD is not connected")
        return self._context

    def _stock_quote_sync(self, symbol: str) -> dict[str, Any]:
        from futu import RET_OK

        result, data = self._require_context().get_stock_quote([f"US.{symbol}"])
        if result != RET_OK or data.empty:
            raise ProviderUnavailableError(f"Futu quote unavailable for {symbol}")
        row = data.iloc[0]
        return {"price": row.get("last_price"), "bid": row.get("bid_price"), "ask": row.get("ask_price"), "volume": row.get("volume"), "delayed": None}

    async def stock_quote(self, symbol: str) -> dict[str, Any]:
        return await self._run(self._stock_quote_sync, symbol)

    def _option_chain_sync(self, symbol: str, expiry: date | datetime | None) -> list[dict[str, Any]]:
        from futu import RET_OK

        result, data = self._require_context().get_option_chain(f"US.{symbol}")
        if result != RET_OK:
            raise ProviderUnavailableError(f"Futu option chain unavailable for {symbol}")
        target = expiry.date().isoformat() if isinstance(expiry, datetime) else expiry.isoformat() if expiry else None
        rows = []
        for _, row in data.iterrows():
            if target and str(row.get("option_expiry_date")) != target:
                continue
            raw_type = str(row.get("option_type", "")).upper()
            if raw_type.startswith("CALL"):
                option_type = "C"
            elif raw_type.startswith("PUT"):
                option_type = "P"
            else:
                continue
            rows.append({"code": str(row["code"]), "expiry": str(row["option_expiry_date"]), "strike": row["strike_price"], "option_type": option_type})
        return rows

    async def option_chain(self, symbol: str, expiry: date | datetime | None) -> list[dict[str, Any]]:
        return await self._run(self._option_chain_sync, symbol, expiry)

    def _option_quote_sync(self, code: str) -> dict[str, Any]:
        from futu import RET_OK, SubType

        context = self._require_context()
        result, detail = context.subscribe([code], [SubType.QUOTE], subscribe_push=False)
        if result != RET_OK:
            raise ProviderUnavailableError("Futu option quote subscription failed")
        try:
            result, data = context.get_stock_quote([code])
            if result != RET_OK or data.empty:
                raise ProviderUnavailableError("Futu option quote unavailable")
            row = data.iloc[0]
            return {"bid": row.get("bid_price"), "ask": row.get("ask_price"), "last": row.get("last_price"), "volume": row.get("volume"), "open_interest": row.get("option_open_interest"), "implied_volatility": row.get("option_implied_volatility"), "delayed": None}
        finally:
            context.unsubscribe([code], [SubType.QUOTE])

    async def option_quote(self, code: str) -> dict[str, Any]:
        return await self._run(self._option_quote_sync, code)
