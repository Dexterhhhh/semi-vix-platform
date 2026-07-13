import asyncio
import sys
import types

from app.data.providers.futu.client import FutuClient
from app.data.providers.ibkr.client import IBKRClient


class _RowTable:
    empty = False

    class _ILoc:
        def __getitem__(self, _: int):
            return {"bid_price": 1.0, "ask_price": 1.2, "last_price": 1.1, "volume": 2, "option_open_interest": 3, "option_implied_volatility": 0.4}

    iloc = _ILoc()


def test_futu_client_releases_mocked_quote_subscription(monkeypatch) -> None:
    class FakeContext:
        last = None

        def __init__(self, **_):
            self.subscribed = []
            self.unsubscribed = []
            FakeContext.last = self

        def subscribe(self, codes, subtypes, **_kwargs):
            self.subscribed.append((codes, subtypes))
            return 0, None

        def get_stock_quote(self, _codes):
            return 0, _RowTable()

        def unsubscribe(self, codes, subtypes):
            self.unsubscribed.append((codes, subtypes))
            return 0, None

        def close(self):
            self.closed = True

    fake_module = types.SimpleNamespace(RET_OK=0, SubType=types.SimpleNamespace(QUOTE="QUOTE"), OpenQuoteContext=FakeContext)
    monkeypatch.setitem(sys.modules, "futu", fake_module)

    async def check() -> None:
        client = FutuClient("127.0.0.1", 11111)
        await client.connect()
        stock = await client.stock_quote("NVDA")
        assert stock["price"] == 1.1
        assert FakeContext.last.subscribed == [(["US.NVDA"], ["QUOTE"])]
        quote = await client.option_quote("US.NVDA260821C00100000")
        assert quote["last"] == 1.1
        assert FakeContext.last.unsubscribed == [(["US.NVDA"], ["QUOTE"]), (["US.NVDA260821C00100000"], ["QUOTE"])]
        await client.disconnect()
        await client.disconnect()
    asyncio.run(check())


def test_ibkr_client_cancels_mocked_market_data_subscription(monkeypatch) -> None:
    class Contract:
        def __init__(self, symbol, sec_type="STK", *args, **kwargs):
            self.symbol = symbol
            self.secType = sec_type
            self.conId = 7

    class FakeTicker:
        bid = 99.0
        ask = 101.0
        last = 100.0
        volume = 10
        modelGreeks = None

        @staticmethod
        def marketPrice():
            return 100.0

    class FakeIB:
        last = None

        def __init__(self):
            self.connected = False
            self.cancelled = []
            FakeIB.last = self

        def connect(self, *_args, **_kwargs):
            self.connected = True

        def disconnect(self):
            self.connected = False

        def isConnected(self):
            return self.connected

        def qualifyContracts(self, contract):
            return [contract]

        def reqMktData(self, _contract, *_args):
            return FakeTicker()

        def sleep(self, _seconds):
            return None

        def cancelMktData(self, contract):
            self.cancelled.append(contract)

    fake_module = types.SimpleNamespace(IB=FakeIB, Stock=lambda symbol, exchange, currency: Contract(symbol), Option=lambda symbol, expiry, strike, right, exchange, **kwargs: Contract(symbol, "OPT"))
    monkeypatch.setitem(sys.modules, "ib_insync", fake_module)

    async def check() -> None:
        client = IBKRClient("127.0.0.1", 7497, 1, market_data_timeout=0)
        await client.connect()
        quote = await client.stock_quote("NVDA")
        assert quote["price"] == 100.0
        assert len(FakeIB.last.cancelled) == 1
        await client.disconnect()
        await client.disconnect()
    asyncio.run(check())
