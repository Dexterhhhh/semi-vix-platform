import pytest
from fastapi.testclient import TestClient

from app import bridge
from app.database.database import Base, SessionLocal, engine
from app.database.models import ProviderCredential


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(bridge.app, client=("127.0.0.1", 12345)) as instance:
        yield instance


def configure(provider):
    with SessionLocal() as database:
        database.add(ProviderCredential(provider=provider, enabled=True, host="localhost",
                                        port=7497, client_id=19))
        database.commit()


def test_bridge_only_accepts_loopback(client):
    assert client.get("/health").status_code == 200
    with TestClient(bridge.app, client=("192.0.2.1", 12345)) as external:
        assert external.get("/health").status_code == 403
        assert external.post("/internal/providers/collect", json={"symbols": ["AAPL"]}).status_code == 403


def test_collection_requires_symbols_and_active_sdk_configuration(client):
    assert client.post("/internal/providers/collect").status_code == 422
    assert client.post("/internal/providers/collect", json={"symbols": []}).status_code == 422
    assert client.post("/internal/providers/collect", json={"symbols": ["AAPL"]}).status_code == 409
    configure("ALPACA")
    assert client.post("/internal/providers/collect", json={"symbols": ["AAPL"]}).status_code == 409


@pytest.mark.parametrize("provider_name", ["IBKR", "FUTU"])
def test_collection_uses_go_selected_symbols_and_injected_sdk(client, monkeypatch, provider_name):
    configure(provider_name)
    sdk = object()
    def factory(provider, **kwargs):
        assert provider == provider_name
        assert kwargs == {"host": "localhost", "port": 7497, "client_id": 19}
        return sdk
    async def collect(symbols, database, provider):
        assert symbols == ["AAPL", "NVDA"]
        assert provider is sdk
        assert database.query(ProviderCredential).count() == 1
        return {"provider": provider_name, "symbols_requested": len(symbols)}
    monkeypatch.setattr(bridge, "create_vendor_provider", factory)
    monkeypatch.setattr(bridge, "collect_option_snapshot", collect)
    response = client.post("/internal/providers/collect", json={"symbols": ["AAPL", "NVDA"]})
    assert response.status_code == 200
    assert response.json() == {"provider": provider_name, "symbols_requested": 2}
