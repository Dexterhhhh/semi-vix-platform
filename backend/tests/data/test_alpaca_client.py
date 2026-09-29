import asyncio
from datetime import date
import httpx
import pytest

from app.data.exceptions import ProviderRateLimitError
from app.data.providers.alpaca.client import AlpacaClient, parse_occ_symbol


def test_occ_symbol_parser() -> None:
    parsed = parse_occ_symbol("NVDA260821P00125000")
    assert parsed["expiry"].date() == date(2026, 8, 21)
    assert parsed["expiry"].hour == 21
    assert parsed["strike"] == 125.0
    assert parsed["option_type"] == "P"


def test_chain_pagination_is_cached_for_quote_calls(monkeypatch) -> None:
    calls: list[tuple[str, dict | None]] = []

    async def fake_request(self, path: str, params=None):
        calls.append((path, dict(params) if params else None))
        if len(calls) == 1:
            return {"snapshots": {"NVDA260821C00100000": {"latestQuote": {"bp": 1.0, "ap": 1.2}}}, "next_page_token": "next"}
        return {"snapshots": {"NVDA260821P00100000": {"latestQuote": {"bp": 0.9, "ap": 1.1}}}}

    monkeypatch.setattr(AlpacaClient, "_request", fake_request)

    async def check() -> None:
        client = AlpacaClient("key", "secret")
        rows = await client.option_chain("NVDA", date(2026, 8, 21))
        assert len(rows) == 2
        quote = await client.option_quote("NVDA260821C00100000")
        assert quote["bid"] == 1.0
        assert len(calls) == 2
        assert calls[1][1]["page_token"] == "next"

    asyncio.run(check())


def test_retry_after_is_preserved_for_rate_limit() -> None:
    class RateLimitedHTTP:
        async def get(self, path, params=None):
            return httpx.Response(429, headers={"Retry-After": "120"}, request=httpx.Request("GET", "https://data.alpaca.markets" + path))

    async def check() -> None:
        client = AlpacaClient("key", "secret")
        client._http = RateLimitedHTTP()
        with pytest.raises(ProviderRateLimitError) as error:
            await client._request("/v2/stocks/SPY/snapshot")
        assert error.value.retry_after_seconds == 120

    asyncio.run(check())
