from datetime import datetime
from typing import Any, Optional
from app.data.exceptions import ProviderUnavailableError


class FutuClient:
    """Thin quotation-only Futu OpenD client; it never imports trading contexts."""

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self._context: Any = None

    async def connect(self) -> None:
        try:
            from futu import OpenQuoteContext
            self._context = OpenQuoteContext(host=self.host, port=self.port)
        except Exception as exc:
            self._context = None
            raise ProviderUnavailableError(f"Futu OpenD connection failed: {exc}") from exc

    async def disconnect(self) -> None:
        if self._context:
            self._context.close()

    async def health_check(self) -> bool:
        if not self._context:
            return False
        try:
            from futu import RET_OK
            result, _ = self._context.get_global_state()
            return result == RET_OK
        except Exception:
            return False

    def _require_context(self) -> Any:
        if not self._context:
            raise ProviderUnavailableError("Futu OpenD is not connected")
        return self._context

    async def stock_quote(self, symbol: str) -> dict[str, Any]:
        from futu import RET_OK
        result, data = self._require_context().get_stock_quote([f"US.{symbol}"])
        if result != RET_OK or data.empty:
            raise ProviderUnavailableError(f"Futu quote unavailable for {symbol}")
        row = data.iloc[0]
        return {"price": row.get("last_price"), "bid": row.get("bid_price"), "ask": row.get("ask_price"), "volume": row.get("volume")}

    async def option_chain(self, symbol: str, expiry: Optional[datetime]) -> list[dict[str, Any]]:
        from futu import RET_OK
        result, data = self._require_context().get_option_chain(f"US.{symbol}")
        if result != RET_OK:
            raise ProviderUnavailableError(f"Futu option chain unavailable for {symbol}")
        target = expiry.date().isoformat() if expiry else None
        rows = []
        for _, row in data.iterrows():
            if target and str(row.get("option_expiry_date")) != target:
                continue
            right = "C" if str(row.get("option_type", "")).upper().startswith("CALL") else "P"
            rows.append({"code": str(row["code"]), "expiry": str(row["option_expiry_date"]), "strike": float(row["strike_price"]), "option_type": right})
        return rows

    async def option_quote(self, code: str) -> dict[str, Any]:
        from futu import RET_OK, SubType
        context = self._require_context()
        result, detail = context.subscribe([code], [SubType.QUOTE], subscribe_push=False)
        if result != RET_OK:
            raise ProviderUnavailableError(f"Futu quote subscription failed: {detail}")
        result, data = context.get_stock_quote([code])
        if result != RET_OK or data.empty:
            raise ProviderUnavailableError(f"Futu option quote unavailable: {code}")
        row = data.iloc[0]
        return {"bid": row.get("bid_price"), "ask": row.get("ask_price"), "last": row.get("last_price"), "volume": row.get("volume"), "open_interest": row.get("option_open_interest"), "implied_volatility": row.get("option_implied_volatility")}
