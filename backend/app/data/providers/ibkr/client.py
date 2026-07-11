"""Read-only TWS / IB Gateway client built on ``ib_insync``.

The wrapper serializes the synchronous SDK on a worker thread.  It deliberately
uses short-lived market-data subscriptions and always cancels them after a
snapshot, so a web request never leaks an IBKR subscription.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

from app.data.exceptions import ProviderUnavailableError
from app.data.normalization import optional_float


class IBKRClient:
    def __init__(self, host: str, port: int, client_id: int, market_data_timeout: float = 3.0, max_option_strikes: int = 60):
        self.host, self.port, self.client_id = host, port, client_id
        self.market_data_timeout = market_data_timeout
        self.max_option_strikes = max_option_strikes
        self._ib: Any = None
        self._operation_lock = None

    async def _run(self, function, *args):
        if self._operation_lock is None:
            self._operation_lock = asyncio.Lock()
        async with self._operation_lock:
            return await asyncio.to_thread(function, *args)

    def _connected(self) -> bool:
        return bool(self._ib and self._ib.isConnected())

    def _connect_sync(self) -> None:
        if self._connected():
            return
        try:
            from ib_insync import IB

            ib = IB()
            ib.connect(self.host, self.port, clientId=self.client_id, readonly=True, timeout=10)
            self._ib = ib
        except Exception as exc:
            self._ib = None
            raise ProviderUnavailableError("IBKR connection failed") from exc

    async def connect(self) -> None:
        await self._run(self._connect_sync)

    def _disconnect_sync(self) -> None:
        if self._connected():
            self._ib.disconnect()
        self._ib = None

    async def disconnect(self) -> None:
        await self._run(self._disconnect_sync)

    async def health_check(self) -> bool:
        return await self._run(self._connected)

    def _require_connection(self) -> Any:
        if not self._connected():
            raise ProviderUnavailableError("IBKR is not connected")
        return self._ib

    def _discover_stock_sync(self, symbol: str) -> Any:
        from ib_insync import Stock

        contracts = self._require_connection().qualifyContracts(Stock(symbol, "SMART", "USD"))
        if not contracts:
            raise ProviderUnavailableError(f"IBKR contract discovery failed for {symbol}")
        return contracts[0]

    async def discover_stock(self, symbol: str) -> Any:
        return await self._run(self._discover_stock_sync, symbol)

    def _snapshot_sync(self, contract: Any) -> dict[str, Any]:
        ib = self._require_connection()
        ticker = ib.reqMktData(contract, "", False, False)
        try:
            ib.sleep(self.market_data_timeout)
            return {
                "price": ticker.marketPrice(),
                "bid": ticker.bid,
                "ask": ticker.ask,
                "last": ticker.last,
                "volume": ticker.volume,
                "open_interest": getattr(ticker, "putOpenInterest", None) or getattr(ticker, "callOpenInterest", None),
                "implied_volatility": getattr(getattr(ticker, "modelGreeks", None), "impliedVol", None),
                "delayed": None,
            }
        finally:
            ib.cancelMktData(contract)

    def _stock_quote_sync(self, symbol: str) -> dict[str, Any]:
        return self._snapshot_sync(self._discover_stock_sync(symbol))

    async def stock_quote(self, symbol: str) -> dict[str, Any]:
        return await self._run(self._stock_quote_sync, symbol)

    def _option_chain_sync(self, symbol: str, expiry: date | datetime | None) -> list[dict[str, Any]]:
        ib = self._require_connection()
        stock = self._discover_stock_sync(symbol)
        chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        target = expiry.strftime("%Y%m%d") if expiry else None
        chain = next((item for item in chains if item.exchange == "SMART" and (target is None or target in item.expirations)), None)
        if chain is None:
            return []
        expiration = target or min(chain.expirations)
        underlying_price = optional_float(self._snapshot_sync(stock).get("price"))
        strikes = sorted(float(value) for value in chain.strikes if float(value) > 0)
        if len(strikes) > self.max_option_strikes:
            reference = underlying_price if underlying_price is not None else strikes[len(strikes) // 2]
            strikes = sorted(sorted(strikes, key=lambda value: abs(value - reference))[: self.max_option_strikes])
        return [{"symbol": symbol, "expiry": expiration, "strike": strike, "option_type": right} for strike in strikes for right in ("C", "P")]

    async def option_chain(self, symbol: str, expiry: date | datetime | None) -> list[dict[str, Any]]:
        return await self._run(self._option_chain_sync, symbol, expiry)

    def _option_quote_sync(self, symbol: str, expiry: str, strike: float, option_type: str) -> dict[str, Any]:
        from ib_insync import Option

        contracts = self._require_connection().qualifyContracts(Option(symbol, expiry, strike, option_type, "SMART", currency="USD", multiplier="100"))
        if not contracts:
            raise ProviderUnavailableError("IBKR option contract discovery failed")
        return self._snapshot_sync(contracts[0])

    async def option_quote(self, symbol: str, expiry: str, strike: float, option_type: str) -> dict[str, Any]:
        return await self._run(self._option_quote_sync, symbol, expiry, strike, option_type)
