from datetime import datetime
from typing import Any, Optional
from app.data.exceptions import ProviderUnavailableError


class IBKRClient:
    """Thin, quotation-only TWS/IB Gateway client using contract discovery before quotes."""

    def __init__(self, host: str, port: int, client_id: int):
        self.host, self.port, self.client_id = host, port, client_id
        self._ib: Any = None

    async def connect(self) -> None:
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id, readonly=True, timeout=10)
        except Exception as exc:
            self._ib = None
            raise ProviderUnavailableError(f"IBKR connection failed: {exc}") from exc

    async def disconnect(self) -> None:
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()

    async def health_check(self) -> bool:
        return bool(self._ib and self._ib.isConnected())

    def _require_connection(self) -> Any:
        if not self._ib or not self._ib.isConnected():
            raise ProviderUnavailableError("IBKR is not connected")
        return self._ib

    async def discover_stock(self, symbol: str) -> Any:
        from ib_insync import Stock
        ib = self._require_connection()
        contracts = ib.qualifyContracts(Stock(symbol, "SMART", "USD"))
        if not contracts:
            raise ProviderUnavailableError(f"IBKR contract discovery failed for {symbol}")
        return contracts[0]

    async def option_chain(self, symbol: str, expiry: Optional[datetime]) -> list[dict[str, Any]]:
        ib = self._require_connection()
        stock = await self.discover_stock(symbol)
        chains = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        target = expiry.strftime("%Y%m%d") if expiry else None
        chain = next((item for item in chains if item.exchange == "SMART" and (not target or target in item.expirations)), None)
        if not chain:
            return []
        expiration = target or min(chain.expirations)
        return [{"symbol": symbol, "expiry": expiration, "strike": float(strike), "option_type": right} for strike in chain.strikes for right in ("C", "P")]

    async def stock_quote(self, symbol: str) -> dict[str, Any]:
        ib = self._require_connection()
        contract = await self.discover_stock(symbol)
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(1)
        return {"price": ticker.marketPrice(), "bid": ticker.bid, "ask": ticker.ask, "volume": ticker.volume}

    async def option_quote(self, symbol: str, expiry: str, strike: float, option_type: str) -> dict[str, Any]:
        from ib_insync import Option
        ib = self._require_connection()
        contracts = ib.qualifyContracts(Option(symbol, expiry, strike, option_type, "SMART", currency="USD"))
        if not contracts:
            raise ProviderUnavailableError("IBKR option contract discovery failed")
        ticker = ib.reqMktData(contracts[0], "", False, False)
        ib.sleep(1)
        greeks = ticker.modelGreeks
        return {"bid": ticker.bid, "ask": ticker.ask, "last": ticker.last, "volume": ticker.volume, "open_interest": None, "implied_volatility": greeks.impliedVol if greeks else None}
